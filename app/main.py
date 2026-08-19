from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional
from pydantic import BaseModel
import re
from datetime import datetime

load_dotenv()

app = FastAPI(
    title="Unspoken Backend",
    description="Lead Management Service",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

async def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise Exception("DATABASE_URL environment variable is not configured")
    
    if database_url.startswith("postgresql://"):
        match = re.search(r'@([^:/]+)(?=/)', database_url)
        if match:
            host = match.group(1)
            if f"@{host}/" in database_url:
                database_url = database_url.replace(f"@{host}/", f"@{host}:5432/")
    
    try:
        conn = await asyncpg.connect(dsn=database_url)
        print("✅ PostgreSQL connection successful")
        return conn
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        raise


# ============================================================
# MODELS
# ============================================================

class LeadCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Unspoken Backend",
        "status": "running",
        "endpoints": [
            "POST /api/leads - Save a new lead",
            "GET /api/leads - Get all leads",
            "GET /api/leads/{email} - Get lead by email",
            "GET /api/health - Health check"
        ]
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/health")
async def health():
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetchrow("SELECT NOW() AS current_time")
        return {
            "status": "API is running",
            "database": "Connected",
            "timestamp": result["current_time"]
        }
    except Exception as e:
        return {
            "status": "API running but database connection failed",
            "error": str(e)
        }
    finally:
        if conn:
            await conn.close()


# ============================================================
# LEADS ENDPOINTS
# ============================================================

@app.post("/api/leads")
async def save_lead(lead: LeadCreate):
    """
    Save a new lead. Email is the unique identifier.
    """
    conn = None
    try:
        # Validate
        if not lead.full_name or not lead.email:
            return {
                "success": False,
                "message": "full_name and email are required"
            }

        print("=" * 50)
        print("📥 LEAD RECEIVED")
        print(f"Name  : {lead.full_name}")
        print(f"Email : {lead.email}")
        print(f"Phone : {lead.phone}")
        print("=" * 50)

        conn = await get_db()

        # Check if lead already exists
        existing_lead = await conn.fetchrow(
            """
            SELECT full_name, email, phone, created_at
            FROM leads
            WHERE email = $1
            """,
            lead.email
        )

        if existing_lead:
            print("✅ Lead already exists:", lead.email)
            return {
                "success": True,
                "message": "Lead already exists",
                "lead": dict(existing_lead)
            }

        # Insert new lead
        await conn.execute(
            """
            INSERT INTO leads (full_name, email, phone, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            """,
            lead.full_name,
            lead.email,
            lead.phone
        )

        print("✅ Lead saved successfully:", lead.email)

        return {
            "success": True,
            "message": "Lead saved successfully"
        }

    except Exception as e:
        print(f"❌ Error saving lead: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    finally:
        if conn:
            await conn.close()


@app.get("/api/leads")
async def get_all_leads():
    """
    Get all leads.
    """
    conn = None
    try:
        conn = await get_db()

        leads = await conn.fetch(
            """
            SELECT full_name, email, phone, created_at
            FROM leads
            ORDER BY created_at DESC
            """
        )

        return {
            "success": True,
            "leads": [dict(lead) for lead in leads],
            "count": len(leads)
        }

    except Exception as e:
        print(f"❌ Error fetching leads: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    finally:
        if conn:
            await conn.close()


@app.get("/api/leads/{email}")
async def get_lead_by_email(email: str):
    """
    Get a lead by email address.
    """
    conn = None
    try:
        conn = await get_db()

        lead = await conn.fetchrow(
            """
            SELECT full_name, email, phone, created_at
            FROM leads
            WHERE email = $1
            """,
            email
        )

        if not lead:
            return {
                "success": False,
                "message": "Lead not found"
            }

        return {
            "success": True,
            "lead": dict(lead)
        }

    except Exception as e:
        print(f"❌ Error fetching lead: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    finally:
        if conn:
            await conn.close()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
