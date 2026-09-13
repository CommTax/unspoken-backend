# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Server
    PORT = int(os.environ.get('PORT', 5000))
    
    # AI
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Frontend
    FRONTEND_URL = os.environ.get('FRONTEND_URL', '*')
    
    # ============================================================
    # RAZORPAY (NEW)
    # ============================================================
    RAZORPAY_KEY_ID = os.environ.get('rzp_live_TN9VVH5DwiHx0L', '')
    RAZORPAY_KEY_SECRET = os.environ.get('VVm0T6QsbLGlRxbM63uMV7JL', '')
    
    # ============================================================
    # JWT SESSION TOKENS (NEW)
    # ============================================================
    JWT_SECRET = os.environ.get('JWT_SECRET', 'change_this_in_production')
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRY_HOURS = 24
    
    # Archetype codes
    ARCHETYPES = ['SIM', 'PER', 'THI', 'CUR', 'PRE', 'CON', 'EMV']
    
    # Voice dimension mapping
    VOICE_DIMENSIONS = {
        'clarity': {'SIM': 0.4, 'THI': 0.3, 'CUR': 0.2, 'PRE': 0.1},
        'structure': {'THI': 0.4, 'SIM': 0.3, 'CUR': 0.2, 'PRE': 0.1},
        'confidence': {'PRE': 0.4, 'PER': 0.3, 'EMV': 0.2, 'CON': 0.1},
        'presence': {'PRE': 0.5, 'PER': 0.3, 'CON': 0.1, 'THI': 0.1},
        'connection': {'CON': 0.5, 'EMV': 0.2, 'PRE': 0.2, 'SIM': 0.1},
        'influence': {'PER': 0.5, 'PRE': 0.2, 'CON': 0.2, 'SIM': 0.1}
    }
