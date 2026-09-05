from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import (
    CommunicationRequest,
    PremiumCommunicationAnalysisRequest,
    PremiumCommunicationAnalysisResponse,
    AnalysisMode,
    QuestionType
)
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.utils.scenarios import SCENARIOS
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================
# EXISTING ENDPOINT - Deep Communication Analysis
# ============================================================

@router.post("/analyze")
async def analyze_communication(request: CommunicationRequest):
    """
    Communication Analysis for Front Page Testing.
    This handles the voice/text practice and provides feedback.
    """
    try:
        print("=" * 60)
        print("🧠 THE UNSPOKEN AI ANALYST")
        print(f"Scenario: {request.scenario_id}")
        
        # Extract attempts
        attempts_data = []
        
        if request.attempts:
            attempts_data = [{
                'attempt': a.attempt,
                'response': a.response,
                'mode': a.mode
            } for a in request.attempts]
        elif request.response:
            attempts_data = [{
                'attempt': request.attempt or 1,
                'response': request.response,
                'mode': request.mode or 'text'
            }]
            if request.previous_attempts:
                for prev in request.previous_attempts:
                    attempts_data.insert(0, {
                        'attempt': prev.get('attempt', 1),
                        'response': prev.get('response', ''),
                        'mode': prev.get('mode', 'text')
                    })
        else:
            return {"success": False, "message": "No attempt data provided"}
        
        if len(attempts_data) > 3:
            return {"success": False, "message": "Maximum 3 attempts allowed per scenario."}
        
        # Create service instance
        service = AnalysisService()
        
        # Call the analysis service
        result = await service.analyze_communication_deep(
            scenario_id=request.scenario_id,
            attempts_data=attempts_data
        )
        
        return result
        
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


@router.get("/scenarios")
async def get_scenarios():
    """Get all practice scenarios."""
    return {"success": True, "scenarios": SCENARIOS}


# ============================================================
# NEW ENDPOINT - Premium Communication Analysis
# ============================================================

@router.post("/analyze/premium", response_model=PremiumCommunicationAnalysisResponse)
async def analyze_premium_communication(
    request: PremiumCommunicationAnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service)
):
    """
    Premium Communication Analysis with comprehensive metrics.
    
    This endpoint provides detailed analysis including:
    - Clarity, Precision, Structure, Impact, Influence scores
    - Communication gap analysis (What You Meant vs What Landed)
    - Behavioral evidence and detected patterns
    - Instant mirror (first 10 seconds audit)
    - Before & after rewrite
    - Signal-to-noise ratio
    - Attention waveform
    - Pattern diagnosis
    
    **Request Body:**
    - `text`: The user's response text (required)
    - `mode`: Analysis mode - 'voice' or 'text' (required)
    - `question_type`: Question type - 'intro' or 'project' (required)
    - `user_id`: Optional user ID for tracking
    - `scenario_id`: Optional scenario ID for context
    """
    try:
        logger.info(f"Premium analysis request received - Mode: {request.mode}, Question: {request.question_type}")
        
        # Validate text length
        if not request.text or len(request.text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Text must be at least 10 characters long"
            )
        
        # Get analysis from service
        response = await service.analyze_premium_communication(request)
        
        logger.info("Premium analysis completed successfully")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Premium analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


# ============================================================
# SUPPORTING ENDPOINTS
# ============================================================

@router.get("/analysis/modes")
async def get_analysis_modes():
    """Get available analysis modes."""
    return {
        "success": True,
        "modes": [
            {"value": "voice", "label": "Voice (45s)"},
            {"value": "text", "label": "Type (60s)"}
        ]
    }


@router.get("/analysis/question-types")
async def get_question_types():
    """Get available question types."""
    return {
        "success": True,
        "question_types": [
            {"value": "intro", "label": "Introduce Yourself", "prompt": "Tell me about yourself — your background, what you do, and what drives you professionally."},
            {"value": "project", "label": "Current Project", "prompt": "Tell me about a current project or initiative you're leading or involved in."}
        ]
    }


@router.get("/analysis/health")
async def analysis_health_check():
    """Health check for analysis service."""
    return {
        "status": "healthy",
        "service": "communication-analysis",
        "endpoints": [
            "/api/communication/analyze",
            "/api/communication/analyze/premium",
            "/api/communication/scenarios",
            "/api/communication/analysis/modes",
            "/api/communication/analysis/question-types"
        ]
    }


# ============================================================
# BATCH ANALYSIS ENDPOINT (Optional)
# ============================================================

@router.post("/analyze/batch")
async def analyze_batch_communication(
    requests: List[PremiumCommunicationAnalysisRequest],
    service: AnalysisService = Depends(get_analysis_service)
):
    """
    Analyze multiple communications in batch.
    Useful for processing multiple scenarios or attempts.
    """
    try:
        results = []
        for request in requests:
            try:
                result = await service.analyze_premium_communication(request)
                results.append({
                    "success": True,
                    "request": {
                        "mode": request.mode,
                        "question_type": request.question_type,
                        "text_preview": request.text[:50] + "..."
                    },
                    "response": result.dict()
                })
            except Exception as e:
                results.append({
                    "success": False,
                    "request": {
                        "mode": request.mode,
                        "question_type": request.question_type,
                        "text_preview": request.text[:50] + "..."
                    },
                    "error": str(e)
                })
        
        return {
            "success": True,
            "results": results,
            "total": len(results),
            "successful": sum(1 for r in results if r["success"])
        }
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch analysis failed: {str(e)}"
        )


# ============================================================
# EXPORT ROUTER
# ============================================================

# Note: The router is imported and used in main.py
# All endpoints are accessible at /api/communication/*
