# app/routes/checkout.py

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timedelta
import hmac
import hashlib
import uuid
import razorpay

from app.config import Config
from app.database import (
    create_paid_user_and_session,
    get_user_by_session_token,
)

router = APIRouter()


# ============================================================
# RAZORPAY CLIENT FACTORY — creates a fresh client per call
# ============================================================
def get_razorpay_client():
    """
    Creates a fresh Razorpay client using the CURRENT env values.
    This avoids the "stale client" bug where the client is bound at
    module import time and never picks up env var changes.
    """
    key_id = Config.RAZORPAY_KEY_ID
    key_secret = Config.RAZORPAY_KEY_SECRET

    # Diagnostic prints so we can see what values are being used
    print("🔎 Razorpay client init — KEY_ID prefix:", (key_id or "EMPTY")[:12])
    print("🔎 Razorpay client init — SECRET length:", len(key_secret or ""))

    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET is not set in the environment"
        )

    return razorpay.Client(auth=(key_id, key_secret))


# ============================================================
# PLAN PRICING (in paise)
# ============================================================
PLAN_PRICING = {
    "sprint": 149900,   # ₹1,499
    "pass": 399900,     # ₹3,999
}


# ============================================================
# REQUEST MODELS
# ============================================================
class CreateOrderRequest(BaseModel):
    plan: str
    sprint: str
    name: str
    email: str
    phone: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan: str
    sprint: str
    name: str
    email: str
    phone: str


# ============================================================
# ENDPOINT 1: CREATE RAZORPAY ORDER
# ============================================================
@router.post("/create-order")
async def create_order(req: CreateOrderRequest):
    if req.plan not in PLAN_PRICING:
        raise HTTPException(status_code=400, detail="Invalid plan")

    amount = PLAN_PRICING[req.plan]

    try:
        # ✅ Create the client fresh, using current env vars
        client = get_razorpay_client()

        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": f"rcpt_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "plan": req.plan,
                "sprint": req.sprint,
                "name": req.name,
                "email": req.email,
                "phone": req.phone,
            }
        })
        return {
            "order_id": order["id"],
            "amount": amount,
            "currency": "INR"
        }
    except Exception as e:
        import traceback
        print("❌ Razorpay create order FAILED")
        print("❌ Error:", repr(e))
        print("❌ KEY_ID prefix:", (Config.RAZORPAY_KEY_ID or "EMPTY")[:12])
        print("❌ KEY_ID length:", len(Config.RAZORPAY_KEY_ID or ""))
        print("❌ KEY_SECRET length:", len(Config.RAZORPAY_KEY_SECRET or ""))
        print("❌ KEY_SECRET has space:", " " in (Config.RAZORPAY_KEY_SECRET or ""))
        print("❌ KEY_SECRET has quote:", '"' in (Config.RAZORPAY_KEY_SECRET or ""))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create order")


# ============================================================
# ENDPOINT 2: VERIFY PAYMENT & CREATE PAID USER
# ============================================================
@router.post("/verify-payment")
async def verify_payment(req: VerifyPaymentRequest):
    # 1. Verify Razorpay signature
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected_signature = hmac.new(
        Config.RAZORPAY_KEY_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, req.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # 2. Compute plan expiry
    if req.plan == "sprint":
        duration_days = 28
    elif req.plan == "pass":
        duration_days = 365
    else:
        raise HTTPException(status_code=400, detail="Invalid plan")

    # 3. Create user + session + payments + transactions
    try:
        result = await create_paid_user_and_session(
            name=req.name,
            email=req.email,
            phone=req.phone,
            plan=req.plan,
            sprint=req.sprint,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature,
            amount=PLAN_PRICING[req.plan],
            duration_days=duration_days,
        )
    except Exception as e:
        print(f"❌ DB save error: {repr(e)}")
        raise HTTPException(status_code=500, detail="Failed to save user")

    return {
        "user_id": result["user_id"],
        "session_token": result["session_token"],
        "plan": req.plan,
        "sprint": req.sprint,
    }


# ============================================================
# ENDPOINT 3: VERIFY SESSION (called by product page)
# ============================================================
@router.post("/verify-session")
async def verify_session(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    user = await get_user_by_session_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    if not user.get("is_paid"):
        return {"is_paid": False}

    return {
        "is_paid": True,
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "phone": user["phone"],
        "plan": user["plan"],
        "sprint": user["sprint"],
        "sprint_start_date": str(user["sprint_start_date"]),
        "sprint_end_date": str(user["sprint_end_date"]),
        "current_day": user["current_day"],
        "total_days": user["total_days"],
    }
