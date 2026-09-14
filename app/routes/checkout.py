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
# RAZORPAY CLIENT
# ============================================================
razorpay_client = razorpay.Client(
    auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET)
)

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
    plan: str        # "sprint" or "pass"
    sprint: str      # "interview", "gd", "leadership", "storytelling", "charisma"
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
        order = razorpay_client.order.create({
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
        print(f"❌ Razorpay create order error: {repr(e)}")
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
    """
    Called by the product page to check if a session token is:
      - A paid session → return full user + plan
      - A drill session → return { is_paid: False } so product page falls back to drill flow
      - Invalid → 401
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")

    user = await get_user_by_session_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # If the session has no plan, it's a drill session
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
