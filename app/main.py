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
import json
from datetime import datetime

load_dotenv()

app = FastAPI(
    title="Unspoken Backend",
    description="Communication Tax Analysis Service",
    version="1.0.0"
)

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
        conn = await asyncpg.connect(dsn=database_url)
        print("✅ PostgreSQL connection successful")
        return conn
    except Exception as db_error:
        print(f"❌ PostgreSQL connection failed: {db_error}")
        raise

# ============================================================
# MODELS
# ============================================================
class UserDetails(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None

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
# ROOT & HEALTH
# ============================================================
@app.get("/")
async def root():
    return {"service": "Unspoken Backend", "status": "running", "docs": "/docs"}

@app.get("/api/health")
async def health():
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetchrow("SELECT NOW() AS current_time")
        return {"status": "✅ API is running!", "database": "Connected", "timestamp": result["current_time"]}
    except Exception as e:
        return {"status": "⚠️ API running but database connection failed", "error": str(e)}
    finally:
        if conn:
            await conn.close()

# ============================================================
# SESSIONS
# ============================================================
@app.post("/api/sessions")
async def create_session():
    conn = None
    try:
        conn = await get_db()
        session_id = str(uuid.uuid4())
        await conn.execute(
            """INSERT INTO assessment_sessions (session_id, status, started_at)
               VALUES ($1, 'started', NOW())""",
            session_id
        )
        return {"success": True, "session_id": session_id, "status": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.put("/api/sessions/{session_id}/category")
async def update_session_category(session_id: str, data: CategoryUpdateRequest):
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
        return {"success": True, "session_id": session_id, "user_category": data.user_category}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# QUESTIONS - CATEGORY
# ============================================================
@app.get("/api/questions/{category_code}")
async def get_category_questions(category_code: str):
    """Get the 10 category-specific assessment questions."""
    conn = None

    try:
        conn = await get_db()

        rows = await conn.fetch(
            """
            SELECT
                category_question_id,
                category_code,
                question_number,
                question_text,
                is_voice,
                voice_prompt,
                option_a,
                option_b,
                option_c,
                option_d,
                option_e,
                option_f,
                option_g,
                display_order
            FROM category_questions
            WHERE category_code = $1
            ORDER BY display_order
            """,
            category_code
        )

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No questions found for category: {category_code}"
            )

        questions = []

        for row in rows:

            # Build options for choice questions
            options = []

            if not row["is_voice"]:
                option_columns = [
                    "option_a",
                    "option_b",
                    "option_c",
                    "option_d",
                    "option_e",
                    "option_f",
                    "option_g"
                ]

                for column in option_columns:
                    value = row[column]

                    if value:
                        options.append(value)

            questions.append({
                "question_code": row["question_number"],
                "category_question_id": row["category_question_id"],
                "question_text": row["question_text"],
                "is_voice": row["is_voice"],
                "question_type": "voice" if row["is_voice"] else "choice",
                "voice_prompt": row["voice_prompt"] if row["is_voice"] else None,
                "options": options,
                "display_order": row["display_order"]
            })

        print(
            f"✅ Loaded {len(questions)} questions "
            f"for category: {category_code}"
        )

        return {
            "success": True,
            "category": category_code,
            "questions": questions
        }

    except HTTPException:
        raise

    except Exception as e:
        print(
            f"❌ Error fetching category questions "
            f"for {category_code}: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            await conn.close()

# ============================================================
# QUESTIONS - INITIAL & COMMON
# ============================================================
@app.get("/api/questions/initial")
async def get_initial_question():
    """Get the initial routing question (Step 2)"""
    conn = None
    try:
        conn = await get_db()
        
        # Get the initial question
        question = await conn.fetchrow(
            """SELECT question_code, question_text, question_type, 
                      options, voice_prompt
               FROM questions 
               WHERE question_code = 'A' AND is_active = true
               LIMIT 1"""
        )
        
        if not question:
            # Fallback hardcoded question
            return {
                "success": True,
                "question": {
                    "question_text": "Who are you becoming?",
                    "options": [
                        {"label": "Building my career", "value": "building"},
                        {"label": "Stepping up", "value": "stepping-up"},
                        {"label": "Leading with influence", "value": "leading"},
                        {"label": "Preparing for what's next", "value": "nextmove"},
                        {"label": "Redefining my next chapter", "value": "redefining"},
                        {"label": "Building my business", "value": "business"}
                    ]
                }
            }
        
        # Parse options if stored as JSON
        options = question["options"]
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except:
                options = []
        
        return {
            "success": True,
            "question": {
                "question_text": question["question_text"],
                "options": options
            }
        }
    except Exception as e:
        print(f"❌ Error getting initial question: {e}")
        # Return fallback
        return {
            "success": True,
            "question": {
                "question_text": "Who are you becoming?",
                "options": [
                    {"label": "Building my career", "value": "building"},
                    {"label": "Stepping up", "value": "stepping-up"},
                    {"label": "Leading with influence", "value": "leading"},
                    {"label": "Preparing for what's next", "value": "nextmove"},
                    {"label": "Redefining my next chapter", "value": "redefining"},
                    {"label": "Building my business", "value": "business"}
                ]
            }
        }
    finally:
        if conn:
            await conn.close()

@app.get("/api/questions/common")
async def get_common_question():
    """Get the common question (Step 3)"""
    conn = None
    try:
        conn = await get_db()
        
        # Get the common question
        question = await conn.fetchrow(
            """SELECT question_code, question_text, question_type, 
                      options, voice_prompt
               FROM questions 
               WHERE question_code = 'B' AND is_active = true
               LIMIT 1"""
        )
        
        if not question:
            # Fallback hardcoded question
            return {
                "success": True,
                "question": {
                    "question_text": "What do you want to achieve?",
                    "options": [
                        {"label": "🚀 Advance career", "value": "career"},
                        {"label": "💪 Feel more confident", "value": "confident"},
                        {"label": "✨ Develop a stronger presence", "value": "presence"},
                        {"label": "🗣️ Become more persuasive", "value": "persuasive"},
                        {"label": "🧘 Overcome social anxiety", "value": "anxiety"},
                        {"label": "🤝 Be understood by others", "value": "understood"}
                    ]
                }
            }
        
        # Parse options if stored as JSON
        options = question["options"]
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except:
                options = []
        
        return {
            "success": True,
            "question": {
                "question_text": question["question_text"],
                "options": options
            }
        }
    except Exception as e:
        print(f"❌ Error getting common question: {e}")
        # Return fallback
        return {
            "success": True,
            "question": {
                "question_text": "What do you want to achieve?",
                "options": [
                    {"label": "🚀 Advance career", "value": "career"},
                    {"label": "💪 Feel more confident", "value": "confident"},
                    {"label": "✨ Develop a stronger presence", "value": "presence"},
                    {"label": "🗣️ Become more persuasive", "value": "persuasive"},
                    {"label": "🧘 Overcome social anxiety", "value": "anxiety"},
                    {"label": "🤝 Be understood by others", "value": "understood"}
                ]
            }
        }
    finally:
        if conn:
            await conn.close()

# ============================================================
# RESPONSES
# ============================================================
@app.post("/api/responses")
async def submit_response(data: ResponseSubmitRequest):
    conn = None

    try:
        if not data.session_id or not data.question_code:
            raise HTTPException(
                status_code=400,
                detail="session_id and question_code are required"
            )

        conn = await get_db()

        # ----------------------------------------------------
        # Verify session
        # ----------------------------------------------------
        session = await conn.fetchrow(
            """
            SELECT session_id
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            data.session_id
        )

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        # ----------------------------------------------------
        # First check universal questions A / B
        # ----------------------------------------------------
        question = await conn.fetchrow(
            """
            SELECT question_id, question_type
            FROM questions
            WHERE question_code = $1
              AND is_active = true
            """,
            data.question_code
        )

        response_type = (
            "choice"
            if data.selected_option
            else "text"
        )

        # ----------------------------------------------------
        # A / B
        # ----------------------------------------------------
        if question:

            await conn.execute(
                """
                INSERT INTO responses
                (
                    session_id,
                    question_id,
                    selected_option,
                    text_response,
                    response_type
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                data.session_id,
                question["question_id"],
                data.selected_option,
                data.text_response,
                response_type
            )

        else:

            # ------------------------------------------------
            # Category question Q1-Q10
            # ------------------------------------------------
            category_question = await conn.fetchrow(
                """
                SELECT category_question_id, is_voice
                FROM category_questions
                WHERE question_number = $1
                AND category_code = (
                    SELECT user_category
                    FROM assessment_sessions
                    WHERE session_id = $2
                )
                """,
                data.question_code,
                data.session_id
            )

            if not category_question:
                raise HTTPException(
                    status_code=404,
                    detail=f"Question {data.question_code} not found"
                )

            response_type = (
                "voice"
                if category_question["is_voice"]
                else (
                    "choice"
                    if data.selected_option
                    else "text"
                )
            )

            await conn.execute(
                """
                INSERT INTO responses
                (
                    session_id,
                    category_question_id,
                    selected_option,
                    text_response,
                    response_type
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                data.session_id,
                category_question["category_question_id"],
                data.selected_option,
                data.text_response,
                response_type
            )

        return {
            "success": True,
            "message": "Response saved successfully",
            "question_code": data.question_code
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"❌ Error saving response: {e}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            await conn.close()
        # ----------------------------------------------------
        # 1. Verify session exists
        # ----------------------------------------------------
        session = await conn.fetchrow(
            """
            SELECT session_id, user_id, user_category
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            data.session_id
        )

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        # ----------------------------------------------------
        # 2. Find the question
        # ----------------------------------------------------
        question = await conn.fetchrow(
            """
            SELECT question_id, question_code, question_type
            FROM questions
            WHERE question_code = $1
            """,
            data.question_code
        )

        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Question not found: {data.question_code}"
            )

        # ----------------------------------------------------
        # 3. Determine response type
        # ----------------------------------------------------
        if data.selected_option:
            response_type = "choice"
        elif data.text_response:
            response_type = "text"
        else:
            response_type = "unknown"

        # ----------------------------------------------------
        # 4. Save response
        #
        # NO user_id here.
        # Session identifies the anonymous assessment.
        # ----------------------------------------------------
        response_id = await conn.fetchval(
            """
            INSERT INTO responses
            (
                session_id,
                question_id,
                selected_option,
                text_response,
                response_type
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING response_id
            """,
            data.session_id,
            question["question_id"],
            data.selected_option,
            data.text_response,
            response_type
        )

        print("==========================================")
        print("✅ RESPONSE SAVED")
        print("Session ID       :", data.session_id)
        print("Question Code    :", data.question_code)
        print("Question ID      :", question["question_id"])
        print("Selected Option  :", data.selected_option)
        print("Response Type    :", response_type)
        print("Response ID      :", response_id)
        print("==========================================")

        return {
            "success": True,
            "message": "Response saved successfully",
            "response_id": str(response_id),
            "session_id": data.session_id,
            "question_code": data.question_code
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ RESPONSE SAVE ERROR")
        print("Error type:", type(e).__name__)
        print("Error:", str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            await conn.close()

# ============================================================
# VOICE ANALYSIS
# ============================================================
@app.post("/api/voice/analyze")
async def analyze_voice(data: VoiceAnalysisRequest):

    conn = None

    try:
        if not data.session_id or not data.transcript:
            raise HTTPException(
                status_code=400,
                detail="session_id and transcript are required"
            )

        conn = await get_db()

        # ----------------------------------------------------
        # 1. Verify session
        # ----------------------------------------------------
        session = await conn.fetchrow(
            """
            SELECT session_id, user_id, user_category
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            data.session_id
        )

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        # ----------------------------------------------------
        # 2. Find voice question
        # ----------------------------------------------------
        question = await conn.fetchrow(
            """
            SELECT question_id, question_code, question_type
            FROM questions
            WHERE question_code = $1
            """,
            data.question_code
        )

        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Voice question not found: {data.question_code}"
            )

        # ----------------------------------------------------
        # 3. Save transcript
        #
        # NO user_id.
        # ----------------------------------------------------
        response_id = await conn.fetchval(
            """
            INSERT INTO responses
            (
                session_id,
                question_id,
                response_type,
                text_response
            )
            VALUES ($1, $2, 'voice', $3)
            RETURNING response_id
            """,
            data.session_id,
            question["question_id"],
            data.transcript
        )

        # ----------------------------------------------------
        # 4. Temporary voice analysis
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # 5. Save voice analysis
        # ----------------------------------------------------
        await conn.execute(
            """
            INSERT INTO voice_analysis
            (
                response_id,
                clarity_score,
                structure_score,
                confidence_score,
                presence_score,
                connection_score,
                influence_score,
                overall_score,
                analysis_json
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            response_id,
            analysis["clarity"],
            analysis["structure"],
            analysis["confidence"],
            analysis["presence"],
            analysis["connection"],
            analysis["influence"],
            analysis["overall"],
            json.dumps(analysis)
        )

        print("==========================================")
        print("🎙️ VOICE RESPONSE SAVED")
        print("Session ID   :", data.session_id)
        print("Question     :", data.question_code)
        print("Response ID  :", response_id)
        print("==========================================")

        return {
            "success": True,
            "response_id": str(response_id),
            "analysis": analysis
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ VOICE ANALYSIS ERROR")
        print("Error type:", type(e).__name__)
        print("Error:", str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            await conn.close()

# ============================================================
# ASSESSMENT COMPLETION
# ============================================================
@app.post("/api/assessment/complete")
async def complete_assessment(data: AssessmentCompleteRequest):
    conn = None
    try:
        if not data.session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        
        conn = await get_db()
        session = await conn.fetchrow(
            "SELECT session_id, user_id, user_category FROM assessment_sessions WHERE session_id = $1",
            data.session_id
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        user_id = session["user_id"]
        if data.user_details and data.user_details.email:
            existing_user = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                data.user_details.email
            )
            if existing_user:
                user_id = existing_user["user_id"]
            else:
                user_id = await conn.fetchval(
                    """INSERT INTO users (full_name, email, phone) 
                       VALUES ($1, $2, $3) 
                       RETURNING user_id""",
                    data.user_details.full_name, data.user_details.email, data.user_details.phone
                )
            
            if user_id:
                await conn.execute(
                    "UPDATE assessment_sessions SET user_id = $1 WHERE session_id = $2",
                    user_id, data.session_id
                )
        
        # Get responses
        responses = await conn.fetch(
            """SELECT q.question_code, r.selected_option, r.text_response
               FROM responses r JOIN questions q ON r.question_id = q.question_id
               WHERE r.session_id = $1""",
            data.session_id
        )
        
        # Simple scoring
        scores = {'SIM': 0, 'PER': 0, 'THI': 0, 'CUR': 0, 'PRE': 0, 'CON': 0, 'EMV': 0}
        
        for response in responses:
            if response.get('selected_option'):
                if response['question_code'].startswith('Q'):
                    scores['SIM'] += 1
                else:
                    scores['PER'] += 1
        
        top_archetype = max(scores, key=scores.get)
        
        archetype = await conn.fetchrow(
            "SELECT archetype_code, archetype_name, description FROM archetypes WHERE archetype_code = $1",
            top_archetype
        )
        
        await conn.execute(
            """INSERT INTO assessment_results 
               (session_id, user_id, archetype_code, overall_score, score_breakdown, result_text)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            data.session_id, user_id, top_archetype, scores[top_archetype],
            json.dumps(scores),
            f"Your primary archetype is {archetype['archetype_name'] if archetype else top_archetype}"
        )
        
        await conn.execute(
            "UPDATE assessment_sessions SET status = 'completed', completed_at = NOW() WHERE session_id = $1",
            data.session_id
        )
        
        return {
            "success": True,
            "session_id": data.session_id,
            "user_id": user_id,
            "archetype_code": top_archetype,
            "archetype_name": archetype["archetype_name"] if archetype else top_archetype,
            "archetype_description": archetype["description"] if archetype else "",
            "scores": scores,
            "overall_score": scores[top_archetype]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# ASSESSMENT RESULT
# ============================================================
@app.get("/api/assessment/result/{session_id}")
async def get_assessment_result(session_id: str):
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
        
        result = await conn.fetchrow(
            """SELECT archetype_code, overall_score, score_breakdown, result_text, created_at
               FROM assessment_results WHERE session_id = $1""",
            session_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Result not found")
        
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
# ARCHETYPES
# ============================================================
@app.get("/api/archetypes")
async def get_archetypes():
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT archetype_id, archetype_code, archetype_name, description,
                      key_traits, strengths, growth_areas, communication_style
               FROM archetypes ORDER BY archetype_id"""
        )
        return {"success": True, "archetypes": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()
