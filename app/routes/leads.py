from fastapi import APIRouter
from app.models.schemas import LeadCreate
from app.services.lead_service import save_lead, get_all_leads, get_lead_by_email

router = APIRouter()

@router.post("/leads")
async def save_lead_endpoint(lead: LeadCreate):
    """
    Store user lead information in database.
    """
    try:
        return await save_lead(lead)
    except Exception as e:
        print(f"❌ Lead save error: {e}")
        return {"success": False, "message": str(e)}

@router.get("/leads")
async def get_all_leads_endpoint():
    """Get all leads from database."""
    try:
        return await get_all_leads()
    except Exception as e:
        print(f"❌ Error fetching leads: {e}")
        return {"success": False, "message": str(e)}

@router.get("/leads/{email}")
async def get_lead_by_email_endpoint(email: str):
    """Get a specific lead by email."""
    try:
        return await get_lead_by_email(email)
    except Exception as e:
        print(f"❌ Error fetching lead: {e}")
        return {"success": False, "message": str(e)}
