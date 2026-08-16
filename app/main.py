from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from urllib.parse import urlparse
import re
import uuid
import json
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
class UserDetails(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None

class SessionCreateResponse(BaseModel):
    session_id: str
    status: str = "started"

class CategoryUpdateRequest(BaseModel):
    user_category: str

class ResponseSubmitRequest(BaseModel):
    session_id: str
    question_code: str
    selected_option: Optional[str] = None
    text_response: Optional[str] = None

class VoiceAnalysisRequest(BaseModel):
    session_id: str
    question_code: str
    transcript: str

class AssessmentCompleteRequest(BaseModel):
    session_id: str
    user_details: Optional[UserDetails] = None

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
# 1. SESSIONS
# ============================================================
@app.post("/api/sessions")
async def create_session():
    """Create a new assessment session"""
    conn = None
    try:
        conn = await get_db()
        session_id = str(uuid.uuid4())
        
        await conn.execute(
            """INSERT INTO assessment_sessions 
               (session_id, status, started_at)
               VALUES ($1, 'started', NOW())""",
            session_id
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "status": "started"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.put("/api/sessions/{session_id}/category")
async def update_session_category(session_id: str, data: CategoryUpdateRequest):
    """Update the category for a session"""
    conn = None
    try:
        conn = await get_db()
        
        session = await conn.fetchrow(
            "SELECT session_id FROM assessment_sessions WHERE session_id = $1",
            session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        await conn.execute(
            "UPDATE assessment_sessions SET user_category = $1 WHERE session_id = $2",
            data.user_category, session_id
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "user_category": data.user_category
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# 2. QUESTIONS
# ============================================================
@app.get("/api/questions/{category_code}")
async def get_category_questions(category_code: str):
    """Get all questions for a specific category"""
    conn = None
    try:
        conn = await get_db()
        
        # Get category-specific questions
        rows = await conn.fetch(
            """SELECT question_code, question_text, question_type, 
                      options, voice_prompt, display_order
               FROM questions 
               WHERE category = $1 AND is_active = true
               ORDER BY display_order""",
            category_code
        )
        
        if not rows:
            # If no category-specific questions, return default
            raise HTTPException(status_code=404, detail="Questions not found for this category")
        
        questions = []
        for row in rows:
            questions.append({
                "question_code": row["question_code"],
                "question_text": row["question_text"],
                "question_type": row["question_type"],
                "options": row["options"] if row["question_type"] == "choice" else [],
                "voice_prompt": row["voice_prompt"] if row["question_type"] == "voice" else None,
                "display_order": row["display_order"]
            })
        
        return {
            "success": True,
            "category": category_code,
            "questions": questions
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# 3. RESPONSES
# ============================================================
@app.post("/api/responses")
async def submit_response(data: ResponseSubmitRequest):
    """Save a user response against a session"""
    conn = None
    try:
        if not data.session_id or not data.question_code:
            raise HTTPException(status_code=400, detail="session_id and question_code are required")
        
        conn = await get_db()
        
        # Check if session exists
        session = await conn.fetchrow(
            "SELECT session_id, user_id FROM assessment_sessions WHERE session_id = $1",
            data.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Find the question
        question = await conn.fetchrow(
            "SELECT question_id, question_type FROM questions WHERE question_code = $1",
            data.question_code
        )
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        # Save response
        await conn.execute(
            """INSERT INTO responses 
               (session_id, user_id, question_id, selected_option, text_response, response_type)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            data.session_id,
            session["user_id"],
            question["question_id"],
            data.selected_option,
            data.text_response,
            "choice" if data.selected_option else "text"
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
# 4. VOICE ANALYSIS
# ============================================================
@app.post("/api/voice/analyze")
async def analyze_voice(data: VoiceAnalysisRequest):
    """Analyze a voice transcript against a session"""
    conn = None
    try:
        if not data.session_id or not data.transcript:
            raise HTTPException(status_code=400, detail="session_id and transcript are required")
        
        conn = await get_db()
        
        # Check if session exists
        session = await conn.fetchrow(
            "SELECT session_id, user_id FROM assessment_sessions WHERE session_id = $1",
            data.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Find the question
        question = await conn.fetchrow(
            "SELECT question_id FROM questions WHERE question_code = $1",
            data.question_code
        )
        if not question:
            raise HTTPException(status_code=404, detail="Voice question not found")
        
        # Save transcript as response
        response_id = await conn.fetchval(
            """INSERT INTO responses 
               (session_id, user_id, question_id, response_type, text_response) 
               VALUES ($1, $2, $3, 'voice', $4) 
               RETURNING response_id""",
            data.session_id,
            session["user_id"],
            question["question_id"],
            data.transcript
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
            json.dumps(analysis)
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
# 5. ASSESSMENT COMPLETION
# ============================================================
@app.post("/api/assessment/complete")
async def complete_assessment(data: AssessmentCompleteRequest):
    """Complete the assessment and link session to user"""
    conn = None
    try:
        if not data.session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        conn = await get_db()
        
        # Check if session exists
        session = await conn.fetchrow(
            "SELECT session_id, user_id, user_category FROM assessment_sessions WHERE session_id = $1",
            data.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Process user details if provided
        user_id = session["user_id"]
        if data.user_details and data.user_details.email:
            # Check if user exists
            existing_user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                data.user_details.email
            )
            if existing_user:
                user_id = existing_user["user_id"]
            else:
                # Create new user
                user_id = await conn.fetchval(
                    """INSERT INTO users (full_name, email, phone) 
                       VALUES ($1, $2, $3) 
                       RETURNING user_id""",
                    data.user_details.full_name,
                    data.user_details.email,
                    data.user_details.phone
                )
            
            # Link user to session
            if user_id:
                await conn.execute(
                    "UPDATE assessment_sessions SET user_id = $1 WHERE session_id = $2",
                    user_id, data.session_id
                )
        
        # Get all responses for this session
        responses = await conn.fetch(
            """SELECT 
                q.question_code,
                r.selected_option,
                r.text_response
               FROM responses r
               JOIN questions q ON r.question_id = q.question_id
               WHERE r.session_id = $1""",
            data.session_id
        )
        
        # Get voice analysis scores
        voice_scores = await conn.fetch(
            """SELECT va.clarity_score, va.structure_score, va.confidence_score, 
                      va.presence_score, va.connection_score, va.influence_score, va.overall_score
               FROM voice_analysis va
               JOIN responses r ON va.response_id = r.response_id
               WHERE r.session_id = $1""",
            data.session_id
        )
        
        # Calculate archetype scores
        archetype_scores = await calculate_archetype_scores(conn, responses, voice_scores)
        
        # Find top archetype
        top_archetype = max(archetype_scores, key=archetype_scores.get)
        top_score = archetype_scores[top_archetype]
        
        # Get archetype details
        archetype = await conn.fetchrow(
            "SELECT archetype_code, archetype_name, description FROM archetypes WHERE archetype_code = $1",
            top_archetype
        )
        
        # Save assessment result
        await conn.execute(
            """INSERT INTO assessment_results 
               (session_id, user_id, archetype_code, overall_score, score_breakdown, result_text)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            data.session_id,
            user_id,
            top_archetype,
            top_score,
            json.dumps(archetype_scores),
            f"Your primary archetype is {archetype['archetype_name'] if archetype else top_archetype}"
        )
        
        # Update session status
        await conn.execute(
            """UPDATE assessment_sessions 
               SET status = 'completed', completed_at = NOW() 
               WHERE session_id = $1""",
            data.session_id
        )
        
        return {
            "success": True,
            "session_id": data.session_id,
            "user_id": user_id,
            "archetype_code": top_archetype,
            "archetype_name": archetype["archetype_name"] if archetype else top_archetype,
            "archetype_description": archetype["description"] if archetype else "",
            "scores": archetype_scores,
            "overall_score": top_score
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# 6. ASSESSMENT RESULT
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
        
        # Get assessment result
        result = await conn.fetchrow(
            """SELECT archetype_code, overall_score, score_breakdown, result_text, created_at
               FROM assessment_results WHERE session_id = $1""",
            session_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        
        # Get archetype details
        archetype = await conn.fetchrow(
            "SELECT archetype_code, archetype_name, description FROM archetypes WHERE archetype_code = $1",
            result["archetype_code"]
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "user_id": session["user_id"],
            "status": session["status"],
            "archetype": {
                "code": archetype["archetype_code"] if archetype else result["archetype_code"],
                "name": archetype["archetype_name"] if archetype else result["archetype_code"],
                "description": archetype["description"] if archetype else ""
            } if archetype else None,
            "overall_score": result["overall_score"],
            "score_breakdown": result["score_breakdown"],
            "result_text": result["result_text"],
            "completed_at": result["created_at"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# 7. ARCHETYPES
# ============================================================
@app.get("/api/archetypes")
async def get_archetypes():
    """Get all archetypes"""
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT archetype_id, archetype_code, archetype_name, description,
                      key_traits, strengths, growth_areas, communication_style
               FROM archetypes ORDER BY archetype_id"""
        )
        return {
            "success": True,
            "archetypes": [dict(row) for row in rows]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# HELPER: CALCULATE ARCHETYPE SCORES
# ============================================================
async def calculate_archetype_scores(conn, responses, voice_scores):
    """Calculate archetype scores from responses and voice analysis"""
    scores = {
        'SIM': 0, 'PER': 0, 'THI': 0,
        'CUR': 0, 'PRE': 0, 'CON': 0, 'EMV': 0
    }
    
    # Process choice responses using question_scoring
    for response in responses:
        if response.get('selected_option'):
            scoring = await conn.fetch(
                """SELECT archetype_code, score FROM question_scoring 
                   WHERE question_code = $1 AND option_code = $2""",
                response['question_code'], response['selected_option']
            )
            for row in scoring:
                if row['archetype_code'] in scores:
                    scores[row['archetype_code']] += row['score']
    
    # Process voice scores (if any)
    for voice in voice_scores:
        # Map voice dimensions to archetypes (simplified)
        if voice.get('clarity_score'):
            scores['SIM'] += voice['clarity_score'] * 0.2
            scores['THI'] += voice['clarity_score'] * 0.2
        if voice.get('structure_score'):
            scores['THI'] += voice['structure_score'] * 0.2
        if voice.get('confidence_score'):
            scores['PRE'] += voice['confidence_score'] * 0.2
            scores['PER'] += voice['confidence_score'] * 0.1
        if voice.get('presence_score'):
            scores['PRE'] += voice['presence_score'] * 0.2
        if voice.get('influence_score'):
            scores['PER'] += voice['influence_score'] * 0.2
            scores['PRE'] += voice['influence_score'] * 0.1
    
    return scores
