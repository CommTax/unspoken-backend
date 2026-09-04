from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# ============================================================
# LEAD MODELS
# ============================================================

class LeadCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None

# ============================================================
# USER MODELS
# ============================================================

class UserCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None

# ============================================================
# PERSONA ASSESSMENT MODELS
# ============================================================

class PersonaAssessmentRequest(BaseModel):
    user_details: UserCreate
    responses: List[dict]
    type: str = 'paid'

# ============================================================
# COMMUNICATION ANALYSIS MODELS
# ============================================================

class AttemptData(BaseModel):
    attempt: int
    response: str
    mode: str  # 'voice' or 'text'

class CommunicationRequest(BaseModel):
    scenario_id: int
    attempts: Optional[List[AttemptData]] = None
    response: Optional[str] = None
    attempt: Optional[int] = None
    mode: Optional[str] = None
    previous_attempts: Optional[List[Dict[str, Any]]] = None
