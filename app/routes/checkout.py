# app/routes/checkout.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os
import hmac
import hashlib
import razorpay
import jwt
from datetime import datetime, timedelta

load_dotenv()

router = APIRouter()

# ============================================================
# RAZORPAY CLIENT
# ============================================================
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
JWT_SECRET = os.environ.get("JWT_SECRET", "change_this_secret")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ============================================================
# PRICING
# ============================================================
PLAN_PRICING = {
    "sprint": 149900,   # ₹1,499 in paise
    "pass": 399900,     # ₹3,999 in paise
}


# ============================================================
# REQUEST MODELS
# ============================================================
class CreateOrderRequest(BaseModel):
    plan: str            # "sprint" or "pass"
    sprint: str          # "interview", "gd", "leadership", "storytelling", "charisma"
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
    try:
        if req.plan not in PLAN_PRICING:
            raise HTTPException(status_code=400, detail="Invalid plan")

        amount = PLAN_PRICING[req.plan]

        order = razorpay_client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": f"rcpt_{int(datetime.now().timestamp())}",
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

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Create order error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")


# ============================================================
# ENDPOINT 2: VERIFY PAYMENT & CREATE USER
# ============================================================
@router.post("/verify-payment")
async def verify_payment(req: VerifyPaymentRequest):
    try:
        # 1. Verify Razorpay signature
        body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, req.razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        # 2. Save user to your database
        #    ⚠️ REPLACE THIS with your actual DB logic.
        #    You likely already have a `save_lead` function in app/services/.
        from app.services.database import save_user_and_subscription  # <-- adjust import
        user_id = await save_user_and_subscription(
            name=req.name,
            email=req.email,
            phone=req.phone,
            plan=req.plan,
            sprint=req.sprint,
            payment_id=req.razorpay_payment_id,
            order_id=req.razorpay_order_id,
            amount=PLAN_PRICING[req.plan],
        )

        # 3. Generate session token (JWT)
        session_token = jwt.encode(
            {
                "user_id": user_id,
                "email": req.email,
                "plan": req.plan,
                "sprint": req.sprint,
                "exp": datetime.utcnow() + timedelta(hours=24)
            },
            JWT_SECRET,
            algorithm="HS256"
        )

        return {
            "user_id": user_id,
            "session_token": session_token
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Verify payment error: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed")
