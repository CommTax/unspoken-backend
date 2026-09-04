import asyncpg
from app.utils.helpers import get_db

async def save_lead(lead):
    """Save a lead to the database."""
    conn = None
    try:
        if not lead.full_name or not lead.email:
            return {"success": False, "message": "full_name and email are required"}

        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        # Check if lead exists
        existing_lead = await conn.fetchrow(
            "SELECT full_name, email, phone, created_at FROM leads WHERE email = $1",
            lead.email
        )

        if existing_lead:
            await conn.close()
            return {"success": True, "message": "Lead already exists", "lead": dict(existing_lead)}

        # Insert new lead
        await conn.execute(
            """
            INSERT INTO leads (full_name, email, phone, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            """,
            lead.full_name, lead.email, lead.phone
        )

        await conn.close()
        return {"success": True, "message": "Lead saved successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()

async def get_all_leads():
    """Get all leads from the database."""
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
            
        leads = await conn.fetch(
            "SELECT full_name, email, phone, created_at FROM leads ORDER BY created_at DESC"
        )
        await conn.close()
        return {"success": True, "leads": [dict(lead) for lead in leads], "count": len(leads)}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()

async def get_lead_by_email(email: str):
    """Get a specific lead by email."""
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
            
        lead = await conn.fetchrow(
            "SELECT full_name, email, phone, created_at FROM leads WHERE email = $1",
            email
        )
        await conn.close()
        if not lead:
            return {"success": False, "message": "Lead not found"}
        return {"success": True, "lead": dict(lead)}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()
