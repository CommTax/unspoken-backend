from pydantic import BaseModel
from typing import List, Optional

class CommunicationAnalysis(BaseModel):
    communication_tax_score: int
    clarity_rating: str
    structure_rating: str
    confidence_rating: str
    key_insights: List[str]
    actionable_recommendations: List[str]
    follow_up_questions: List[str]
    estimated_value_leakage: str

class AnalyzeRequest(BaseModel):
    transcript: str
    context: Optional[str] = None

class AnalyzeResponse(BaseModel):
    success: bool
    analysis: Optional[CommunicationAnalysis] = None
    error: Optional[str] = None
