from fastapi import APIRouter
from app.models.schemas import CommunicationRequest
from app.services.analysis_service import analyze_communication_deep
from app.utils.scenarios import SCENARIOS

router = APIRouter()

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
        
        # Call the analysis service
        result = await analyze_communication_deep(
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
