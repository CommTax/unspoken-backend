# app/routes/auth.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import asyncpg
import os
import secrets
import uuid
import resend
from datetime import datetime, timedelta

from app.config import Config

router = APIRouter()

# ============================================================
# RESEND SETUP
# ============================================================
resend.api_key = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@theunspoken.co.in")
FROM_NAME = os.environ.get("RESEND_FROM_NAME", "The Unspoken")


# ============================================================
# REQUEST MODELS
# ============================================================
class RequestOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


# ============================================================
# POST /api/auth/request-otp
# ============================================================
@router.post("/request-otp")
async def request_otp(req: RequestOtpRequest):
    """
    Generates a 6-digit OTP, saves it in session_tokens with a 10-min expiry,
    and emails it via Resend. Only works if user has a paid subscription.
    """
    email = req.email.lower().strip()

    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        # 1. Verify user exists and has a paid plan
        user = await conn.fetchrow(
            "SELECT user_id, full_name FROM users WHERE LOWER(email) = $1",
            email,
        )
        if not user:
            raise HTTPException(
                status_code=404,
                detail="No account found with this email. Please purchase a plan first.",
            )

        sub = await conn.fetchrow(
            """
            SELECT plan, track_id
            FROM user_sessions
            WHERE LOWER(email) = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            email,
        )
        if not sub:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found. Please purchase a plan first.",
            )

        # 2. Generate 6-digit OTP
        otp = str(secrets.randbelow(900000) + 100000)

        # 3. Save as a session_tokens row. We encode "otp:uuid" in jti.
        token_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        jti_value = f"{otp}:{token_id}"

        await conn.execute(
            """
            INSERT INTO session_tokens (jti, email, drill_id, used_at, expires_at, created_at)
            VALUES ($1, $2, NULL, NULL, $3, NOW())
            """,
            jti_value, email, expires_at,
        )

        # 4. Send OTP email via Resend
        try:
            resend.Emails.send({
                "from": f"{FROM_NAME} <{FROM_EMAIL}>",
                "to": [email],
                "subject": f"{otp} is your login code",
                "html": f"""
                    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;background:#faf8f5;">
                      <div style="background:#fff;border-radius:16px;padding:32px;border:1px solid #ede8e0;">
                        <h2 style="font-family:'Playfair Display',Georgia,serif;margin:0 0 16px;color:#1a1917;font-size:22px;">
                          Your login code
                        </h2>
                        <p style="color:#4d4a44;font-size:14px;line-height:1.6;margin:0 0 24px;">
                          Hi {user["full_name"] or "there"}, enter this code to sign in:
                        </p>
                        <div style="background:#faf8f5;border:1px dashed #b8943c;border-radius:12px;padding:24px;text-align:center;margin:24px 0;">
                          <div style="font-size:36px;font-weight:800;letter-spacing:8px;color:#1a1917;font-family:'SF Mono',Menlo,Consolas,monospace;">
                            {otp}
                          </div>
                        </div>
                        <p style="color:#8a8680;font-size:12px;line-height:1.6;margin:24px 0 0;">
                          This code expires in <strong>10 minutes</strong>. If you didn't request this, you can safely ignore this email.
                        </p>
                      </div>
                      <p style="text-align:center;color:#8a8680;font-size:11px;margin-top:20px;">
                        The Unspoken · Understand the gap. Close the gap.
                      </p>
                    </div>
                """,
            })
        except Exception as e:
            print(f"❌ Resend email failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Could not send email. Please try again.",
            )

        return {
            "status": "sent",
            "email": email,
            "message": "Check your inbox for the 6-digit code.",
        }

    finally:
        await conn.close()


# ============================================================
# POST /api/auth/verify-otp
# ============================================================
@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    """
    Verifies the OTP, returns a session token the frontend uses to log in.
    """
    email = req.email.lower().strip()
    otp = req.otp.strip()

    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(status_code=400, detail="Invalid OTP format")

    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        # 1. Find matching OTP row (most recent, unused, not expired)
        row = await conn.fetchrow(
            """
            SELECT jti, email, expires_at
            FROM session_tokens
            WHERE jti LIKE $1
              AND LOWER(email) = $2
              AND used_at IS NULL
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            f"{otp}:%", email,
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired code")

        # 2. Mark OTP as used (one-time use)
        await conn.execute(
            "UPDATE session_tokens SET used_at = NOW() WHERE jti = $1",
            row["jti"],
        )

        # 3. Create a fresh 30-day session token for the user
        session_token = str(uuid.uuid4())
        token_expiry = datetime.utcnow() + timedelta(days=30)
        await conn.execute(
            """
            INSERT INTO session_tokens (jti, email, drill_id, used_at, expires_at, created_at)
            VALUES ($1, $2, NULL, NULL, $3, NOW())
            """,
            session_token, email, token_expiry,
        )

        # 4. Fetch user + plan info
        user = await conn.fetchrow(
            "SELECT user_id, full_name, phone FROM users WHERE LOWER(email) = $1",
            email,
        )
        sub = await conn.fetchrow(
            """
            SELECT plan, track_id, current_day, total_days,
                   sprint_start_date, sprint_end_date
            FROM user_sessions
            WHERE LOWER(email) = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            email,
        )

        return {
            "status": "ok",
            "session_token": session_token,
            "user_id": str(user["user_id"]) if user else None,
            "name": user["full_name"] if user else "Member",
            "email": email,
            "phone": user["phone"] if user else "",
            "plan": sub["plan"] if sub else None,
            "sprint": sub["track_id"] if sub else None,
            "current_day": sub["current_day"] if sub else 1,
            "total_days": sub["total_days"] if sub else 28,
            "sprint_start_date": str(sub["sprint_start_date"]) if sub else None,
            "sprint_end_date": str(sub["sprint_end_date"]) if sub else None,
        }

    finally:
        await conn.close()
