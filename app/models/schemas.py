from pydantic import BaseModel
from typing import List, Optional

class DimensionFeedback(BaseModel):
    rating: str  # "Strong", "Good", "Needs Work", "Critical Gap"
    feedback: str

class SpeechAnalytics(BaseModel):
    words_per_minute: int
    filler_words_per_minute: int
    total_words: int
    total_fillers: int
    filler_word_list: List[str]

class CommunicationAnalysis(BaseModel):
    overall_comment: str
    unspoken_value_score: int  # 0-100, calculated by Gemini
    thinking: DimensionFeedback
    structure: DimensionFeedback
    clarity: DimensionFeedback
    influence: DimensionFeedback
    speech_analytics: SpeechAnalytics  # ✅ MUST HAVE THIS LINE
    good_points: List[str]
    areas_to_cover: List[str]
    follow_up_questions: List[str]

class AnalyzeRequest(BaseModel):
    transcript: str
    context: Optional[str] = None

class AnalyzeResponse(BaseModel):
    success: bool
    analysis: Optional[CommunicationAnalysis] = None
    error: Optional[str] = None
