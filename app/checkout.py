# app/routes/checkout.py — top of the file

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import hmac
import hashlib
import razorpay
import jwt
from datetime import datetime, timedelta

from app.config import Config          # <-- import the class
from app.database import save_user_and_subscription

router = APIRouter()

# Use Config.XXX instead of bare variables
razorpay_client = razorpay.Client(
    auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET)
)

PLAN_PRICING = {
    "sprint": 100,
    "pass": 200,
}
