from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional, List
from pydantic import BaseModel
import re
import uuid
import json
import random
import string
import hashlib
import secrets
from datetime import datetime, timedelta
import razorpay
import hmac

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


class CheckoutRequest(BaseModel):
    full_name: str
    email: str
    phone: str
    type: str = 'persona'
    plan_code: Optional[str] = None


class PaymentVerifyRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class LoginRequest(BaseModel):
    email: str
    password: str


class PersonaAssessmentRequest(BaseModel):
    user_id: str
    responses: List[dict]  # [{"question_code": "Q1", "answer": 5}, ...]
    type: str = 'paid'
    user_details: Optional[dict] = None
    test_mode: Optional[bool] = False


# ============================================================
# HELPERS
# ============================================================

def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=12))


def hash_password(password: str):
    salt = secrets.token_hex(16)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() + ':' + salt


def verify_password(password: str, hashed: str):
    try:
        stored_hash, salt = hashed.split(':')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        return new_hash == stored_hash
    except:
        return False


# ============================================================
# SCORING ENGINE (ADD THIS SECTION)
# ============================================================

def calculate_competency_scores(responses):
    """
    ✅ Backend calculates scores from 30 questions
    ❌ NOT in database
    """
    # Question to category mapping
    category_mapping = {
        'structure': ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6'],
        'thinking': ['Q7', 'Q8', 'Q9', 'Q10', 'Q11', 'Q12'],
        'impact': ['Q13', 'Q14', 'Q15', 'Q16', 'Q17', 'Q18'],
        'expression': ['Q19', 'Q20', 'Q21', 'Q22', 'Q23', 'Q24'],
        'connection': ['Q25', 'Q26', 'Q27', 'Q28', 'Q29', 'Q30']
    }
    
    # Initialize scores
    competency_scores = {
        'structure': 0,
        'thinking': 0,
        'impact': 0,
        'expression': 0,
        'connection': 0
    }
    
    # Process responses
    for r in responses:
        question_code = r.get('question_code')
        answer = r.get('answer')  # 1-5
        
        try:
            score = int(answer)
        except:
            continue
        
        for category, questions in category_mapping.items():
            if question_code in questions:
                competency_scores[category] += score
                break
    
    # Calculate averages (0-100 scale)
    for category in competency_scores:
        competency_scores[category] = round((competency_scores[category] / 6) * 20, 2)
    
    return competency_scores


def get_score_range(score):
    """Determine score range for lookup"""
    if score >= 90:
        return '90-100'
    elif score >= 75:
        return '75-89'
    elif score >= 60:
        return '60-74'
    elif score >= 40:
        return '40-59'
    else:
        return 'Below 40'


def determine_persona(competency_scores):
    """
    ✅ Backend determines persona from scores
    ❌ NOT in database
    """
    # Helper to check levels
    def get_level(score):
        if score >= 80: return 'high'
        if score >= 60: return 'mid'
        return 'low'
    
    levels = {cat: get_level(score) for cat, score in competency_scores.items()}
    
    # Pattern matching logic
    # Check for TRANSLATOR: All dimensions High
    if all(level == 'high' for level in levels.values()):
        return 'TRANSLATOR'
    
    # Check for AMPLIFIER: Impact + Expression stand out
    if levels['impact'] == 'high' and levels['expression'] == 'high':
        return 'AMPLIFIER'
    
    # Check for ARTICULATOR: Structure + Expression stand out
    if levels['structure'] == 'high' and levels['expression'] == 'high':
        return 'ARTICULATOR'
    
    # Check for INTERPRETER: Thinking + Connection stand out
    if levels['thinking'] == 'high' and levels['connection'] == 'high':
        return 'INTERPRETER'
    
    # Check for FILTER: Thinking + Structure strong, Impact lower
    if levels['thinking'] == 'high' and levels['structure'] == 'high' and levels['impact'] == 'low':
        return 'FILTER'
    
    # Check for EMERGING: Low Impact + moderate others
    if levels['impact'] == 'low':
        other_levels = [levels[cat] for cat in ['structure', 'thinking', 'expression', 'connection']]
        if any(level == 'high' for level in other_levels) or all(level != 'low' for level in other_levels):
            return 'EMERGING'
    
    # Check for MISALIGNED: Connection significantly lower than others
    connection_score = competency_scores['connection']
    other_scores = [competency_scores[cat] for cat in ['structure', 'thinking', 'impact', 'expression']]
    avg_other = sum(other_scores) / len(other_scores) if other_scores else 0
    
    if connection_score < avg_other - 15:
        return 'MISALIGNED'
    
    # Default: Articulator
    return 'ARTICULATOR'


# ============================================================
# COMPETENCY LOOKUP (ADD THIS SECTION)
# ============================================================

async def get_competency_writeups(conn, competency_scores):
    """
    ✅ Backend looks up write-ups from database
    ✅ Database stores the content only
    """
    writeups = {}
    
    for competency, score in competency_scores.items():
        score_range = get_score_range(score)
        
        # Database only stores the content, not the logic
        row = await conn.fetchrow(
            """
            SELECT 
                competency,
                score_range,
                category,
                executive_narrative,
                whats_working,
                whats_holding_you_back,
                how_others_experience_you,
                professional_impact,
                highest_roi_improvement
            FROM competency_scores
            WHERE competency = $1 AND score_range = $2
            """,
            competency, score_range
        )
        
        if row:
            writeups[competency] = {
                'score': score,
                'score_range': row['score_range'],
                'category': row['category'],
                'executive_narrative': row['executive_narrative'],
                'whats_working': row['whats_working'],
                'whats_holding_you_back': row['whats_holding_you_back'],
                'how_others_experience_you': row['how_others_experience_you'],
                'professional_impact': row['professional_impact'],
                'highest_roi_improvement': row['highest_roi_improvement']
            }
        else:
            # Fallback if no matching record found
            writeups[competency] = {
                'score': score,
                'score_range': score_range,
                'category': 'Not Available',
                'executive_narrative': 'No narrative available for this score range.',
                'whats_working': '',
                'whats_holding_you_back': '',
                'how_others_experience_you': '',
                'professional_impact': '',
                'highest_roi_improvement': ''
            }
    
    return writeups


# ============================================================
# PAID PERSONA ASSESSMENT ENDPOINT (ADD THIS SECTION)
# ============================================================

@app.post("/api/persona/paid-assess")
async def paid_persona_assessment(data: PersonaAssessmentRequest):
    """
    Submit paid persona assessment responses.
    Scoring is done entirely on the backend.
    """
    conn = None
    try:
        print("=" * 50)
        print("📝 PAID PERSONA ASSESSMENT")
        print(f"User: {data.user_id}")
        print(f"Responses: {len(data.responses)}")
        print("=" * 50)

        conn = await get_db()

        # --- 1. Handle User ---
        user_id = data.user_id
        
        if data.test_mode and data.user_details:
            # Test mode - create or get user
            user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                data.user_details.get('email')
            )
            if not user:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (full_name, email, phone, created_at, has_paid_persona)
                    VALUES ($1, $2, $3, NOW(), TRUE)
                    RETURNING user_id
                    """,
                    data.user_details.get('full_name', 'Test User'),
                    data.user_details.get('email', 'test@example.com'),
                    data.user_details.get('phone', '9999999999')
                )
                print(f"✅ Test user created: {user_id}")
            else:
                user_id = user['user_id']
                await conn.execute(
                    "UPDATE users SET has_paid_persona = TRUE WHERE user_id = $1",
                    user_id
                )
                print(f"✅ Existing user updated: {user_id}")
        else:
            # Verify user exists
            user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE user_id = $1",
                data.user_id
            )
            if not user:
                return {"success": False, "message": "User not found"}
            user_id = data.user_id

        # --- 2. Calculate Competency Scores ---
        competency_scores = calculate_competency_scores(data.responses)
        print(f"📊 Competency Scores: {competency_scores}")

        # --- 3. Determine Persona ---
        persona_code = determine_persona(competency_scores)
        print(f"🧠 Persona: {persona_code}")

        # --- 4. Get Persona Content ---
        persona_content = await conn.fetchrow(
            """
            SELECT 
                persona_code,
                persona_name,
                description,
                detailed_description,
                strength,
                strength_description,
                you_tend_to,
                you_naturally_bring,
                you_may_unintentionally_create,
                greatest_communication_advantage,
                biggest_communication_risk,
                blind_spot,
                blind_spot_description,
                tagline,
                communication_style,
                how_others_experience_you,
                growth_opportunities,
                communication_gap,
                recommended_actions
            FROM persona_content
            WHERE persona_code = $1
            """,
            persona_code
        )

        if not persona_content:
            # Fallback to Articulator
            persona_content = await conn.fetchrow(
                "SELECT * FROM persona_content WHERE persona_code = 'ARTICULATOR'"
            )

        if not persona_content:
            return {"success": False, "message": "Persona content not found"}

        # --- 5. Get Competency Write-ups ---
        competency_writeups = await get_competency_writeups(conn, competency_scores)

        # --- 6. Store Responses ---
        for r in data.responses:
            await conn.execute(
                """
                INSERT INTO paid_responses (user_id, question_code, answer, created_at)
                VALUES ($1, $2, $3, NOW())
                """,
                user_id,
                r.get('question_code'),
                r.get('answer')
            )

        # --- 7. Store Persona Result ---
        await conn.execute(
            """
            INSERT INTO paid_personas (
                user_id,
                persona_code,
                persona_name,
                persona_description,
                strength,
                strength_description,
                blind_spot,
                tagline,
                structure_score,
                thinking_score,
                impact_score,
                expression_score,
                connection_score,
                dimension_percentages
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            user_id,
            persona_content['persona_code'],
            persona_content['persona_name'],
            persona_content['description'],
            persona_content['strength'],
            persona_content['strength_description'],
            persona_content['blind_spot'],
            persona_content['tagline'],
            competency_scores['structure'],
            competency_scores['thinking'],
            competency_scores['impact'],
            competency_scores['expression'],
            competency_scores['connection'],
            json.dumps(competency_scores)
        )

        # --- 8. Mark User as Paid ---
        await conn.execute(
            "UPDATE users SET has_paid_persona = TRUE WHERE user_id = $1",
            user_id
        )

        # --- 9. Build Complete Report ---
        report = {
            "persona": {
                "code": persona_content['persona_code'],
                "name": persona_content['persona_name'],
                "description": persona_content['description'],
                "detailed_description": persona_content['detailed_description'],
                "strength": persona_content['strength'],
                "strength_description": persona_content['strength_description'],
                "you_tend_to": persona_content['you_tend_to'],
                "you_naturally_bring": persona_content['you_naturally_bring'],
                "you_may_unintentionally_create": persona_content['you_may_unintentionally_create'],
                "greatest_communication_advantage": persona_content['greatest_communication_advantage'],
                "biggest_communication_risk": persona_content['biggest_communication_risk'],
                "blind_spot": persona_content['blind_spot'],
                "blind_spot_description": persona_content['blind_spot_description'],
                "tagline": persona_content['tagline'],
                "communication_style": persona_content['communication_style'],
                "how_others_experience_you": persona_content['how_others_experience_you'],
                "growth_opportunities": persona_content['growth_opportunities'],
                "communication_gap": persona_content['communication_gap'],
                "recommended_actions": persona_content['recommended_actions']
            },
            "competencies": competency_writeups,
            "scores": competency_scores
        }

        return {
            "success": True,
            "report": report
        }

    except Exception as e:
        print(f"❌ Assessment error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


# ============================================================
# GET PAID PERSONA REPORT
# ============================================================

@app.get("/api/persona/paid-report/{user_id}")
async def get_paid_persona_report(user_id: str):
    """
    Get the paid persona report for a user.
    """
    conn = None
    try:
        conn = await get_db()

        # Get the latest persona result
        persona = await conn.fetchrow(
            """
            SELECT 
                persona_code,
                persona_name,
                persona_description,
                strength,
                strength_description,
                blind_spot,
                tagline,
                structure_score,
                thinking_score,
                impact_score,
                expression_score,
                connection_score,
                dimension_percentages,
                created_at
            FROM paid_personas
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id
        )

        if not persona:
            return {"success": False, "message": "No persona found for this user"}

        # Get persona content for additional details
        content = await conn.fetchrow(
            """
            SELECT 
                communication_style,
                how_others_experience_you,
                growth_opportunities,
                report_sections
            FROM persona_content
            WHERE persona_code = $1
            """,
            persona['persona_code']
        )

        # Get competency scores
        scores = persona['dimension_percentages']
        if isinstance(scores, str):
            scores = json.loads(scores)

        competency_writeups = await get_competency_writeups(conn, scores)

        return {
            "success": True,
            "report": {
                "persona": {
                    "code": persona['persona_code'],
                    "name": persona['persona_name'],
                    "description": persona['persona_description'],
                    "strength": persona['strength'],
                    "strength_description": persona['strength_description'],
                    "blind_spot": persona['blind_spot'],
                    "tagline": persona['tagline'],
                    "communication_style": content['communication_style'] if content else "",
                    "how_others_experience_you": content['how_others_experience_you'] if content else "",
                    "growth_opportunities": content['growth_opportunities'] if content else ""
                },
                "competencies": competency_writeups,
                "scores": scores,
                "created_at": persona['created_at']
            }
        }

    except Exception as e:
        print(f"❌ Error fetching report: {e}")
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


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
            "GET /api/health - Health check",
            "POST /api/persona/paid-assess - Paid Persona Assessment",
            "GET /api/persona/paid-report/{user_id} - Get Paid Persona Report"
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
