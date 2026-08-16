from pydantic import BaseModel
from typing import Optional, Dict, List
from app.models.user import UserCreate

class ResponseSubmit(BaseModel):
    session_id: str
    question_code: str
    selected_option: Optional[str] = None
    text_response: Optional[str] = None
    voice_url: Optional[str] = None

class VoiceAnalysisRequest(BaseModel):
    session_id: str
    question_code: str  # '06' or '10'
    transcript: str

class AssessmentCompleteRequest(BaseModel):
    session_id: str
    user_details: Optional[UserCreate] = None

class AssessmentResult(BaseModel):
    session_id: str
    archetype_code: str
    archetype_name: str
    archetype_description: str
    persona_code: Optional[str] = None
    persona_name: Optional[str] = None
    scores: Dict[str, int]
    score_breakdown: Dict[str, Dict[str, int]]
