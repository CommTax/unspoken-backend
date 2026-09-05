from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

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
# COMMUNICATION ANALYSIS MODELS (Existing)
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


# ============================================================
# PREMIUM COMMUNICATION ANALYSIS MODELS (NEW)
# ============================================================

class AnalysisMode(str, Enum):
    """Analysis mode enum"""
    VOICE = "voice"
    TEXT = "text"

class QuestionType(str, Enum):
    """Question type enum"""
    INTRO = "intro"
    PROJECT = "project"

# ----- Request Models -----

class PremiumCommunicationAnalysisRequest(BaseModel):
    """Request model for premium communication analysis"""
    text: str
    mode: AnalysisMode
    question_type: QuestionType
    user_id: Optional[str] = None
    scenario_id: Optional[int] = None

# ----- Response Models - Premium Metrics -----

class PremiumMetrics(BaseModel):
    """Premium metrics scores (0-100)"""
    clarity: int
    precision: int
    structure: int
    impact: int
    influence: int

class CommunicationGap(BaseModel):
    """Communication gap analysis"""
    what_you_meant: str
    what_landed: str
    what_got_lost: str
    unspoken_gap: str
    why_it_matters: str

class BehavioralEvidence(BaseModel):
    """Behavioral evidence list"""
    evidence_list: List[str]

class PatternsDetected(BaseModel):
    """Detected patterns list"""
    pattern_list: List[str]

class InstantMirrorAnalysis(BaseModel):
    """First 10 seconds audit"""
    time_to_point: int
    opened_with: str
    actual_point: str
    insight: str

class BeforeAfterRewrite(BaseModel):
    """Before and after rewrite analysis"""
    what_you_said: str
    executive_version: str
    improvement_metrics: Dict[str, Any]

class SignalToNoiseRatio(BaseModel):
    """Signal-to-noise ratio analysis"""
    snr_percentage: int
    noise_percentage: int
    signal_percentage: int
    word_count: int
    needed_words: int
    filler_content: str

class AttentionWaveform(BaseModel):
    """Attention waveform analysis"""
    dropoff_second: int
    wave_data: List[float]
    annotation: str

class PatternDiagnosis(BaseModel):
    """Pattern diagnosis"""
    pattern_name: str
    pattern_description: str
    time_to_point: int
    target_time: int
    impact_score: int
    impact_level: str

# ----- Complete Analysis Response -----

class PremiumCommunicationAnalysisResponse(BaseModel):
    """Complete premium communication analysis response"""
    metrics: PremiumMetrics
    gap: CommunicationGap
    behavioral_evidence: BehavioralEvidence
    patterns_detected: PatternsDetected
    instant_mirror: InstantMirrorAnalysis
    before_after_rewrite: BeforeAfterRewrite
    signal_to_noise: SignalToNoiseRatio
    attention_waveform: AttentionWaveform
    diagnosis: PatternDiagnosis
    timestamp: datetime
    mode: AnalysisMode
    question_type: QuestionType
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ============================================================
# COMMUNICATION ANALYSIS HISTORY MODELS
# ============================================================

class AnalysisHistory(BaseModel):
    """Store analysis history for a user"""
    user_id: str
    analysis_id: str
    text: str
    mode: AnalysisMode
    question_type: QuestionType
    response: PremiumCommunicationAnalysisResponse
    created_at: datetime

class AnalysisHistoryList(BaseModel):
    """List of analysis history"""
    analyses: List[AnalysisHistory]
    total: int
    page: int
    limit: int


# ============================================================
# SCENARIO MODELS (if needed for your existing system)
# ============================================================

class Scenario(BaseModel):
    """Scenario data model"""
    id: int
    title: str
    description: str
    prompt: str
    category: str
    difficulty: Optional[str] = None
    time_limit: Optional[int] = None  # in seconds


# ============================================================
# UTILITY MODELS
# ============================================================

class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[str] = None
