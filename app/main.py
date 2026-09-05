from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Import routes
from app.routes import persona, leads, communication

load_dotenv()

# Create app
app = FastAPI(
    title="Unspoken Backend",
    description="The Unspoken - Communication Analysis & Persona Assessment",
    version="2.0.0"
)

# ============================================================
# CORS MIDDLEWARE
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://theunspoken.co.in",
        "https://www.theunspoken.co.in",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

# ============================================================
# INCLUDE ROUTERS
# ============================================================

# Persona Assessment Routes
app.include_router(persona.router, prefix="/api/persona", tags=["Persona Assessment"])

# Lead Management Routes
app.include_router(leads.router, prefix="/api", tags=["Leads"])

# Communication Analysis Routes (Front Page Testing)
app.include_router(communication.router, prefix="/api/communication", tags=["Communication Analysis"])

# ============================================================
# ROOT & HEALTH ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Unspoken Backend",
        "status": "running",
        "version": "2.0.0",
        "endpoints": {
            "persona": {
                "POST /api/persona/paid-assess": "Full Persona Assessment with Scoring",
                "GET /api/persona/paid-report/{user_id}": "Get Persona Report"
            },
            "leads": {
                "POST /api/leads": "Save Lead",
                "GET /api/leads": "Get All Leads",
                "GET /api/leads/{email}": "Get Lead by Email"
            },
            "communication": {
                "POST /api/communication/analyze": "Communication Analysis (Front Page)",
                "POST /api/communication/analyze/premium": "Premium Communication Analysis with Comprehensive Metrics",
                "GET /api/communication/scenarios": "Get Practice Scenarios",
                "GET /api/communication/analysis/modes": "Get Available Analysis Modes",
                "GET /api/communication/analysis/question-types": "Get Available Question Types",
                "POST /api/communication/analyze/batch": "Batch Communication Analysis"
            }
        }
    }

@app.get("/api/health")
async def health_check():
    from app.services.gemini_client import GEMINI_API_KEY
    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY),
        "database_configured": bool(os.environ.get("DATABASE_URL")),
        "service": "Unspoken Backend",
        "version": "2.0.0",
        "features": {
            "premium_analysis": True,
            "batch_analysis": True,
            "voice_analysis": True,
            "text_analysis": True
        }
    }

@app.get("/api/test-gemini")
async def test_gemini():
    from app.services.gemini_client import test_gemini_api
    return await test_gemini_api()

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
