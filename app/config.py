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
