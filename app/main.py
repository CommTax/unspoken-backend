from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional
from pydantic import BaseModel
from urllib.parse import urlparse
import re
import uuid
from datetime import datetime

# ============================================================
# ENVIRONMENT
# ============================================================
load_dotenv()

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(
    title="Unspoken Backend",
    description="Communication Tax Analysis Service",
    version="1.0.0"
)

# ============================================================
# CORS
# ============================================================
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

    # Ensure port is included
    if database_url and 'postgresql://' in database_url:
        match = re.search(r'@([^:]+)(?::\d+)?/', database_url)
        if match:
            host_part = match.group(1)
            if ':' not in host_part:
                database_url = database_url.replace(
                    f'@{host_part}/',
                    f'@{host_part}:5432/'
                )
                print(f"🔧 Added missing port to DATABASE_URL")

    try:
        parsed = urlparse(database_url)
        print("==========================================")
        print("DATABASE CONNECTION DEBUG")
        print("==========================================")
        print(f"Scheme   : {parsed.scheme}")
        print(f"Host     : {parsed.hostname}")
        print(f"Port     : {parsed.port}")
        print(f"Database : {parsed.path}")
        print(f"Username : {parsed.username}")
        print("Password : [HIDDEN]")
        print("==========================================")
    except Exception as debug_error:
        print(f"Could not parse DATABASE_URL: {debug_error}")

    try:
        conn = await asyncpg.connect(dsn=database_url)
        print("✅ PostgreSQL connection successful")
        return conn
    except Exception as db_error:
        print("❌ PostgreSQL connection failed")
        print(f"Database error: {type(db_error).__name__}: {db_error}")
        raise

# ============================================================
# MODELS
# ============================================================
class UserCreate(BaseModel):
    fullName: str
    email: str
    whatsapp: Optional[str] = None

class SessionCreate(BaseModel):
    user_id: Optional[str] = None
    user_category: Optional[str] = None

class ResponseSubmit(BaseModel):
    session_id: str
    question_code: str
    selected_option: Optional[str] = None
    text_response: Optional[str] = None

class AssessmentCompleteRequest(BaseModel):
    session_id: str
    user_details: Optional[UserCreate] = None

# ============================================================
# ROOT ENDPOINT
# ============================================================
@app.get("/")
async def root():
    return {
        "service": "Unspoken Backend",
        "status": "running",
        "docs": "/docs"
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
            "status": "✅ API is running!",
            "database": "Connected",
            "timestamp": result["current_time"]
        }
    except Exception as e:
        return {
            "status": "⚠️ API running but database connection failed",
            "error": str(e)
        }
    finally:
        if conn:
            await conn.close()

# ============================================================
# SESSIONS ROUTES (SESSION-FIRST)
# ============================================================

@app.post("/api/sessions")
async def create_session(data: SessionCreate = None):
    """Create a new assessment session (no user details required)"""
    conn = None
    try:
        conn = await get_db()
        session_id = str(uuid.uuid4())
        user_id = data.user_id if data else None
        user_category = data.user_category if data else None
        
        await conn.execute(
            """INSERT INTO assessment_sessions 
               (session_id, user_id, user_category, status, started_at)
               VALUES ($1, $2, $3, 'started', NOW())""",
            session_id, user_id, user_category
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "user_id": user_id,
            "user_category": user_category,
            "status": "started"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetchrow(
            """SELECT session_id, user_id, user_category, status, started_at, completed_at
               FROM assessment_sessions WHERE session_id = $1""",
            session_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True, "session": dict(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# RESPONSES ROUTES (USES SESSION_ID)
# ============================================================

@app.post("/api/responses")
async def submit_response(data: dict):
    """Save a user response against a session"""
    conn = None
    try:
        session_id = data.get("session_id")
        question_code = data.get("question_code")
        selected_option = data.get("selected_option")
        text_response = data.get("text_response")
        
        if not session_id or not question_code:
            raise HTTPException(status_code=400, detail="session_id and question_code are required")
        
        conn = await get_db()
        
        # Check if session exists
        session = await conn.fetchrow(
            "SELECT session_id FROM assessment_sessions WHERE session_id = $1",
            session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Find the question
        cat_q = await conn.fetchrow(
            "SELECT category_question_id FROM category_questions WHERE question_number = $1 LIMIT 1",
            question_code
        )
        
        if cat_q:
            await conn.execute(
                """INSERT INTO responses 
                   (session_id, category_question_id, selected_option, response_type, text_response)
                   VALUES ($1, $2, $3, 'choice', $4)""",
                session_id, cat_q['category_question_id'], selected_option, text_response
            )
        else:
            q = await conn.fetchrow(
                "SELECT question_id FROM questions WHERE question_code = $1",
                question_code
            )
            if not q:
                raise HTTPException(status_code=404, detail="Question not found")
            
            await conn.execute(
                """INSERT INTO responses 
                   (session_id, question_id, selected_option, response_type, text_response)
                   VALUES ($1, $2, $3, 'choice', $4)""",
                session_id, q['question_id'], selected_option, text_response
            )
        
        return {"success": True, "message": "Response saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# VOICE ANALYSIS (USES SESSION_ID)
# ============================================================

@app.post("/api/voice/analyze")
async def analyze_voice(data: dict):
    """Analyze a voice transcript against a session"""
    conn = None
    try:
        session_id = data.get("session_id")
        question_code = data.get("question_code")
        transcript = data.get("transcript")
        
        if not session_id or not transcript:
            raise HTTPException(status_code=400, detail="session_id and transcript are required")
        
        conn = await get_db()
        
        # Find the question
        cat_q = await conn.fetchrow(
            """SELECT category_question_id FROM category_questions 
               WHERE question_number = $1 LIMIT 1""",
            f"Q{question_code}"
        )
        
        if not cat_q:
            raise HTTPException(status_code=404, detail="Voice question not found")
        
        # Save transcript
        response_id = await conn.fetchval(
            """INSERT INTO responses 
               (session_id, category_question_id, response_type, text_response) 
               VALUES ($1, $2, 'voice_transcript', $3) 
               RETURNING response_id""",
            session_id, cat_q['category_question_id'], transcript
        )
        
        # Simple analysis (replace with Gemini later)
        analysis = {
            "clarity": 70,
            "structure": 65,
            "confidence": 75,
            "presence": 70,
            "connection": 68,
            "influence": 72,
            "overall": 70,
            "feedback": "Good communication skills with room for improvement."
        }
        
        # Save to voice_analysis
        await conn.execute(
            """INSERT INTO voice_analysis 
               (response_id, clarity_score, structure_score, confidence_score, 
                presence_score, connection_score, influence_score, overall_score, analysis_json)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            response_id,
            analysis['clarity'],
            analysis['structure'],
            analysis['confidence'],
            analysis['presence'],
            analysis['connection'],
            analysis['influence'],
            analysis['overall'],
            str(analysis)
        )
        
        return {"success": True, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# USER ROUTES (ONLY CREATED AT THE END)
# ============================================================

@app.post("/api/users")
async def create_user(user: UserCreate):
    """Create a permanent user (only called at the end)"""
    conn = None
    try:
        conn = await get_db()
        
        # Check if user already exists
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE email = $1",
            user.email
        )
        if existing:
            # Return existing user
            return {
                "success": True,
                "user": {
                    "user_id": existing["user_id"],
                    "full_name": user.fullName,
                    "email": user.email,
                    "whatsapp": user.whatsapp
                },
                "existing": True
            }
        
        result = await conn.fetch(
            """
            INSERT INTO users (full_name, email, whatsapp)
            VALUES ($1, $2, $3)
            RETURNING user_id, full_name, email, whatsapp, created_at
            """,
            user.fullName, user.email, user.whatsapp
        )
        return {
            "success": True,
            "user": {
                "user_id": result[0]["user_id"],
                "full_name": result[0]["full_name"],
                "email": result[0]["email"],
                "whatsapp": result[0]["whatsapp"],
                "created_at": result[0]["created_at"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.put("/api/users/{user_id}")
async def update_user(user_id: str, user: UserCreate):
    """Update user details"""
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetch(
            """
            UPDATE users
            SET full_name = COALESCE($1, full_name),
                email = COALESCE($2, email),
                whatsapp = COALESCE($3, whatsapp),
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = $4
            RETURNING user_id, full_name, email, whatsapp
            """,
            user.fullName, user.email, user.whatsapp, user_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "success": True,
            "user": {
                "user_id": result[0]["user_id"],
                "full_name": result[0]["full_name"],
                "email": result[0]["email"],
                "whatsapp": result[0]["whatsapp"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# QUESTIONS ROUTES
# ============================================================

@app.get("/api/questions/initial")
async def get_initial_question():
    """Get Question A (routing question)"""
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetchrow(
            """SELECT question_code, question_text, options
               FROM questions WHERE is_routing = TRUE"""
        )
        if not result:
            raise HTTPException(status_code=404, detail="Initial question not found")
        return {
            "success": True,
            "question": {
                "question_code": result["question_code"],
                "question_text": result["question_text"],
                "options": result["options"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/questions/common")
async def get_common_question():
    """Get Question B (common question)"""
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetchrow(
            """SELECT question_code, question_text, options
               FROM questions WHERE question_code = 'B'"""
        )
        if not result:
            raise HTTPException(status_code=404, detail="Common question not found")
        return {
            "success": True,
            "question": {
                "question_code": result["question_code"],
                "question_text": result["question_text"],
                "options": result["options"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/questions/category/{category_code}")
async def get_category_questions(category_code: str):
    """Get all questions for a specific category"""
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT question_number, question_text, is_voice, voice_prompt,
                      option_a, option_b, option_c, option_d, option_e, option_f, option_g
               FROM category_questions 
               WHERE category_code = $1 
               ORDER BY display_order""",
            category_code
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Category not found")
        
        questions = []
        for row in rows:
            options = []
            option_labels = ['option_a', 'option_b', 'option_c', 'option_d', 'option_e', 'option_f', 'option_g']
            for label in option_labels:
                if row[label]:
                    options.append(row[label])
            
            questions.append({
                "question_number": row["question_number"],
                "question_text": row["question_text"],
                "is_voice": row["is_voice"],
                "voice_prompt": row["voice_prompt"],
                "options": options if not row["is_voice"] else []
            })
        
        return {
            "success": True,
            "category_code": category_code,
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# ASSESSMENT COMPLETION (LINKS SESSION TO USER)
# ============================================================

@app.post("/api/assessment/complete")
async def complete_assessment(data: AssessmentCompleteRequest):
    """Complete the assessment and link session to user"""
    conn = None
    try:
        session_id = data.session_id
        user_details = data.user_details
        
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        conn = await get_db()
        
        # Check if session exists
        session = await conn.fetchrow(
            "SELECT session_id, user_id FROM assessment_sessions WHERE session_id = $1",
            session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # If user details provided, create/update user
        user_id = session["user_id"]
        if user_details and user_details.email:
            existing_user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                user_details.email
            )
            if existing_user:
                user_id = existing_user["user_id"]
            else:
                user_id = await conn.fetchval(
                    """INSERT INTO users (full_name, email, whatsapp) 
                       VALUES ($1, $2, $3) 
                       RETURNING user_id""",
                    user_details.fullName, user_details.email, user_details.whatsapp
                )
            # Link user to session
            await conn.execute(
                "UPDATE assessment_sessions SET user_id = $1 WHERE session_id = $2",
                user_id, session_id
            )
        
        # Get all responses for this session
        responses = await conn.fetch(
            """SELECT 
                COALESCE(q.question_code, cq.question_number) AS question_code,
                r.selected_option,
                r.text_response
               FROM responses r
               LEFT JOIN questions q ON r.question_id = q.question_id
               LEFT JOIN category_questions cq ON r.category_question_id = cq.category_question_id
               WHERE r.session_id = $1""",
            session_id
        )
        
        # Calculate scores (simplified for now)
        from app.services.archetype_engine import ArchetypeEngine
        engine = ArchetypeEngine(conn)
        result = await engine.calculate_archetype(responses, [])
        
        # Update session status
        await conn.execute(
            """UPDATE assessment_sessions 
               SET status = 'completed', completed_at = NOW() 
               WHERE session_id = $1""",
            session_id
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "user_id": user_id,
            "archetype": result.get("archetype_code"),
            "archetype_name": result.get("archetype_name"),
            "persona": result.get("persona_code"),
            "persona_name": result.get("persona_name"),
            "scores": result.get("scores", {})
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# GET ASSESSMENT RESULT
# ============================================================

@app.get("/api/assessment/result/{session_id}")
async def get_assessment_result(session_id: str):
    """Get assessment results for a session"""
    conn = None
    try:
        conn = await get_db()
        
        session = await conn.fetchrow(
            "SELECT session_id, user_id, status FROM assessment_sessions WHERE session_id = $1",
            session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session["status"] != "completed":
            raise HTTPException(status_code=400, detail="Assessment not completed yet")
        
        return {
            "success": True,
            "session_id": session_id,
            "user_id": session["user_id"],
            "status": session["status"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# ARCHETYPE ROUTES
# ============================================================

@app.get("/api/archetypes")
async def get_archetypes():
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT archetype_id, archetype_name, archetype_code, description,
                      key_traits, strengths, growth_areas, communication_style
               FROM archetypes ORDER BY archetype_id"""
        )
        return {"success": True, "archetypes": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# SERVICES (ARCHETYPE ENGINE)
# ============================================================

class ArchetypeEngine:
    def __init__(self, conn):
        self.conn = conn
    
    async def calculate_archetype(self, responses, voice_scores):
        # Simplified scoring
        scores = {
            'SIM': 0, 'PER': 0, 'THI': 0, 
            'CUR': 0, 'PRE': 0, 'CON': 0, 'EMV': 0
        }
        
        # Count selections
        for response in responses:
            if response.get('selected_option'):
                scoring = await self.conn.fetch(
                    """SELECT archetype_code, score FROM question_scoring 
                       WHERE question_code = $1 AND option_code = $2""",
                    response['question_code'], response['selected_option']
                )
                for row in scoring:
                    if row['archetype_code'] in scores:
                        scores[row['archetype_code']] += row['score']
        
        # Find top archetype
        top_archetype = max(scores, key=scores.get) if scores else 'EMV'
        
        # Get archetype details
        archetype = await self.conn.fetchrow(
            "SELECT code, name, description FROM archetypes WHERE code = $1",
            top_archetype
        )
        
        return {
            "archetype_code": top_archetype,
            "archetype_name": archetype['name'] if archetype else top_archetype,
            "scores": scores
        }
