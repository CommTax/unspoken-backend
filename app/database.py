# app/database.py

import asyncpg
import json
import uuid
from datetime import datetime, timedelta
from app.config import Config


async def get_db():
    """Get a single database connection."""
    return await asyncpg.connect(Config.DATABASE_URL)


async def get_db_pool():
    """Get a database connection pool."""
    return await asyncpg.create_pool(
        Config.DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=60
    )


async def close_db_pool(pool):
    """Close the database connection pool."""
    if pool:
        await pool.close()


# ============================================================
# CHECKOUT — PAID USER CREATION
# ============================================================

async def create_paid_user_and_session(
    name: str,
    email: str,
    phone: str,
    plan: str,
    sprint: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    amount: int,
    duration_days: int,
):
    """
    Creates or updates a user, then creates:
      - user_sessions row (plan + sprint + dates)
      - payments row
      - transactions row
      - session_tokens row (drill_id = NULL → marks it as a paid session)
    Returns { user_id, session_token }
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        async with conn.transaction():
            # ─── 1. Find or create user ───
            user_row = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                email,
            )

            if user_row:
                user_id = user_row["user_id"]
                await conn.execute(
                    """
                    UPDATE users
                    SET full_name = COALESCE(NULLIF(full_name, ''), $1),
                        phone = COALESCE(NULLIF(phone, ''), $2),
                        updated_at = NOW()
                    WHERE user_id = $3
                    """,
                    name, phone, user_id,
                )
            else:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (user_id, full_name, email, phone, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, NOW(), NOW())
                    RETURNING user_id
                    """,
                    uuid.uuid4(), name, email, phone,
                )

            # ─── 2. Compute sprint dates ───
            sprint_start = datetime.utcnow().date()
            sprint_end = sprint_start + timedelta(days=duration_days)

            # ─── 3. Create user_sessions row ───
            await conn.execute(
                """
                INSERT INTO user_sessions (
                    session_id, email, phone, name, plan,
                    track_id, current_day, total_days,
                    questions_per_day, trials_per_question,
                    sprint_start_date, sprint_end_date,
                    current_streak, total_reps,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, 1, $7,
                    2, 2,
                    $8, $9,
                    0, 0,
                    NOW(), NOW()
                )
                """,
                uuid.uuid4(), email, phone, name, plan,
                sprint, duration_days,
                sprint_start, sprint_end,
            )

            # ─── 4. Create payments row ───
            await conn.execute(
                """
                INSERT INTO payments (
                    payment_id, email, gateway, product_type,
                    track_id, amount_inr, currency, status,
                    gateway_order_id, gateway_signature,
                    metadata, created_at, paid_at
                )
                VALUES (
                    $1, $2, 'razorpay', $3,
                    $4, $5, 'INR', 'captured',
                    $6, $7,
                    $8, NOW(), NOW()
                )
                """,
                razorpay_payment_id, email, plan,
                sprint, amount / 100,  # paise → INR
                razorpay_order_id, razorpay_signature,
                json.dumps({"plan": plan, "sprint": sprint, "phone": phone}),
            )

            # ─── 5. Create transactions row ───
            await conn.execute(
                """
                INSERT INTO transactions (
                    transaction_id, user_id, razorpay_payment_id,
                    razorpay_order_id, razorpay_signature,
                    amount, currency, status, type, product_name,
                    metadata, created_at, completed_at, updated_at
                )
                VALUES (
                    $1, $2, $3,
                    $4, $5,
                    $6, 'INR', 'success', 'payment', $7,
                    $8, NOW(), NOW(), NOW()
                )
                """,
                uuid.uuid4(), user_id, razorpay_payment_id,
                razorpay_order_id, razorpay_signature,
                amount, plan,
                json.dumps({"sprint": sprint, "plan": plan, "email": email}),
            )

            # ─── 6. Create session token ───
            session_token = str(uuid.uuid4())
            token_expiry = datetime.utcnow() + timedelta(days=30)

            await conn.execute(
                """
                INSERT INTO session_tokens (
                    jti, email, drill_id, used_at, expires_at, created_at
                )
                VALUES ($1, $2, NULL, NULL, $3, NOW())
                """,
                session_token, email, token_expiry,
            )

            return {
                "user_id": str(user_id),
                "session_token": session_token,
            }

    finally:
        await conn.close()


# ============================================================
# CHECKOUT — SESSION VERIFICATION
# ============================================================

async def get_user_by_session_token(token: str):
    """
    Returns user + plan info if the token is a valid paid session.
    Returns None if token is invalid or expired.
    Returns { is_paid: False } if it's a drill session.
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        token_row = await conn.fetchrow(
            """
            SELECT jti, email, drill_id, expires_at, used_at
            FROM session_tokens
            WHERE jti = $1
            """,
            token,
        )

        if not token_row:
            return None

        if token_row["expires_at"] < datetime.utcnow():
            return None

        # Drill session → not paid
        if token_row["drill_id"] is not None:
            return {"is_paid": False}

        # Paid session → fetch user + user_session
        email = token_row["email"]

        user_row = await conn.fetchrow(
            """
            SELECT user_id, full_name, email, phone
            FROM users
            WHERE email = $1
            """,
            email,
        )

        if not user_row:
            return None

        session_row = await conn.fetchrow(
            """
            SELECT plan, track_id, current_day, total_days,
                   sprint_start_date, sprint_end_date
            FROM user_sessions
            WHERE email = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            email,
        )

        if not session_row:
            return None

        return {
            "is_paid": True,
            "user_id": str(user_row["user_id"]),
            "name": user_row["full_name"],
            "email": user_row["email"],
            "phone": user_row["phone"],
            "plan": session_row["plan"],
            "sprint": session_row["track_id"],
            "sprint_start_date": session_row["sprint_start_date"],
            "sprint_end_date": session_row["sprint_end_date"],
            "current_day": session_row["current_day"],
            "total_days": session_row["total_days"],
        }

    finally:
        await conn.close()
