from fastapi import APIRouter
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.gemini_service import GeminiService

router = APIRouter()
gemini = GeminiService()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_transcript(request: AnalyzeRequest):
    if not request.transcript or len(request.transcript.strip()) < 10:
        return AnalyzeResponse(
            success=False,
            error="Transcript too short. Please speak more clearly."
        )
    
    result = gemini.analyze_transcript(request.transcript)
    
    if not result["success"]:
        return AnalyzeResponse(success=False, error=result["error"])
    
    return AnalyzeResponse(success=True, analysis=result["analysis"])

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
