from pydantic import BaseModel
from typing import List, Optional

class DimensionFeedback(BaseModel):
    rating: str  # "Strong", "Good", "Needs Work", "Critical Gap"
    feedback: str  # Specific, actionable feedback for this dimension

class CommunicationAnalysis(BaseModel):
    # Overall assessment
    overall_comment: str  # Summary of where they stand
    
    # Four core dimensions: Thinking, Structure, Clarity, Influence
    thinking: DimensionFeedback
    structure: DimensionFeedback
    clarity: DimensionFeedback
    influence: DimensionFeedback
    
    # Additional insights
    good_points: List[str]  # What they're doing well
    areas_to_cover: List[str]  # What to focus on improving
    follow_up_questions: List[str]  # Max 2 questions

class AnalyzeRequest(BaseModel):
    transcript: str
    context: Optional[str] = None

class AnalyzeResponse(BaseModel):
    success: bool
    analysis: Optional[CommunicationAnalysis] = None
    error: Optional[str] = None
