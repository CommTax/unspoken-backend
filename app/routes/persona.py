from fastapi import APIRouter, HTTPException
from app.models.schemas import PersonaAssessmentRequest
from app.services.persona_service import process_persona_assessment, get_persona_report

router = APIRouter()

@router.post("/paid-assess")
async def paid_persona_assessment(data: PersonaAssessmentRequest):
    """
    Full Persona Assessment with Scoring and Rubric.
    This handles the complete 30-question assessment.
    """
    try:
        print("=" * 50)
        print("📝 PAID PERSONA ASSESSMENT")
        print(f"Name  : {data.user_details.full_name}")
        print(f"Email : {data.user_details.email}")
        print(f"Phone : {data.user_details.phone}")
        print(f"Responses: {len(data.responses)}")
        print("=" * 50)
        
        return await process_persona_assessment(data)
        
    except Exception as e:
        print(f"❌ Assessment error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}

@router.get("/paid-report/{user_id}")
async def get_paid_persona_report(user_id: str):
    """Get a paid persona report."""
    try:
        return await get_persona_report(user_id)
    except Exception as e:
        print(f"❌ Error fetching report: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}
