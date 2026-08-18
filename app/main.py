from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional
from pydantic import BaseModel
import re
import uuid
import json
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

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
# DATABASE
# ============================================================

async def get_db():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL environment variable is not configured")

    # Add port if missing
    if database_url.startswith("postgresql://"):
        match = re.search(r'@([^:/]+)(?=/)', database_url)

        if match:
            host = match.group(1)

            if f"@{host}/" in database_url:
                database_url = database_url.replace(
                    f"@{host}/",
                    f"@{host}:5432/"
                )

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
# ROOT
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Unspoken Backend",
        "status": "running",
        "docs": "/docs"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
async def health():

    conn = None

    try:
        conn = await get_db()

        result = await conn.fetchrow(
            "SELECT NOW() AS current_time"
        )

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
# CREATE SESSION
# ============================================================

@app.post("/api/sessions")
async def create_session():

    conn = None

    try:

        conn = await get_db()

        session_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO assessment_sessions
            (
                session_id,
                status,
                started_at
            )
            VALUES
            (
                $1,
                'started',
                NOW()
            )
            """,
            session_id
        )

        print("✅ Session created:", session_id)

        return {
            "success": True,
            "session_id": session_id,
            "status": "started"
        }

    except Exception as e:

        print("❌ Session creation error:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


# ============================================================
# SET CATEGORY
# ============================================================

@app.put("/api/sessions/{session_id}/category")
async def update_session_category(
    session_id: str,
    data: CategoryUpdateRequest
):
    conn = None

    try:
        conn = await get_db()

        # Validate category
        allowed_categories = {
            "fresher",
            "senior",
            "manager",
            "transition",
            "business",
            "student",
            "undecided"
        }

        if data.user_category not in allowed_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {data.user_category}"
            )

        # Check session
        session = await conn.fetchrow(
            """
            SELECT session_id
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            session_id
        )

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        # IMPORTANT: Save category
        await conn.execute(
            """
            UPDATE assessment_sessions
            SET user_category = $1
            WHERE session_id = $2
            """,
            data.user_category,
            session_id
        )

        # Verify it was actually saved
        saved = await conn.fetchrow(
            """
            SELECT session_id, user_category
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            session_id
        )

        print("==========================================")
        print("✅ CATEGORY SAVED")
        print("Session ID :", session_id)
        print("Category   :", saved["user_category"])
        print("==========================================")

        return {
            "success": True,
            "session_id": session_id,
            "user_category": saved["user_category"]
        }

    except HTTPException:
        raise

    except Exception as e:
        print("❌ CATEGORY SAVE ERROR:", str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if conn:
            await conn.close()


# ============================================================
# INITIAL QUESTION A
# ============================================================

@app.get("/api/questions/initial")
async def get_initial_question():

    conn = None

    try:

        conn = await get_db()

        question = await conn.fetchrow(
            """
            SELECT
                question_code,
                question_text,
                question_type,
                options
            FROM questions
            WHERE question_code = 'A'
            AND is_active = true
            LIMIT 1
            """
        )

        if not question:

            raise HTTPException(
                status_code=404,
                detail="Initial question A not found"
            )

        options = question["options"]

        if options is None:
            options = []

        elif isinstance(options, str):

            try:
                options = json.loads(options)

            except Exception:
                options = []

        return {
            "success": True,
            "question": {
                "question_code": "A",
                "question_text": question["question_text"],
                "question_type": question["question_type"],
                "options": options
            }
        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ Initial question error:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


# ============================================================
# COMMON QUESTION B
# ============================================================

@app.get("/api/questions/common")
async def get_common_question():

    conn = None

    try:

        conn = await get_db()

        question = await conn.fetchrow(
            """
            SELECT
                question_code,
                question_text,
                question_type,
                options
            FROM questions
            WHERE question_code = 'B'
            AND is_active = true
            LIMIT 1
            """
        )

        if not question:

            raise HTTPException(
                status_code=404,
                detail="Common question B not found"
            )

        options = question["options"]

        if options is None:
            options = []

        elif isinstance(options, str):

            try:
                options = json.loads(options)

            except Exception:
                options = []

        return {
            "success": True,
            "question": {
                "question_code": "B",
                "question_text": question["question_text"],
                "question_type": question["question_type"],
                "options": options
            }
        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ Common question error:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


# ============================================================
# CATEGORY QUESTIONS Q1-Q10
# ============================================================

@app.get("/api/questions/{category_code}")
async def get_category_questions(category_code: str):

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

            options = []

            if not row["is_voice"]:

                for column in [
                    "option_a",
                    "option_b",
                    "option_c",
                    "option_d",
                    "option_e",
                    "option_f",
                    "option_g"
                ]:

                    value = row[column]

                    if value:
                        options.append(value)

            questions.append({

                "question_code": row["question_number"],

                "category_question_id":
                    row["category_question_id"],

                "question_text":
                    row["question_text"],

                "is_voice":
                    row["is_voice"],

                "question_type":
                    "voice" if row["is_voice"] else "choice",

                "voice_prompt":
                    row["voice_prompt"]
                    if row["is_voice"]
                    else None,

                "options": options,

                "display_order":
                    row["display_order"]

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
            f"❌ Error loading questions "
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
# RESPONSES
# ============================================================

@app.post("/api/responses")
async def submit_response(data: ResponseSubmitRequest):

    conn = None

    try:

        # ----------------------------------------------------
        # 1. Validate request
        # ----------------------------------------------------

        if not data.session_id:
            raise HTTPException(
                status_code=400,
                detail="session_id is required"
            )

        if not data.question_code:
            raise HTTPException(
                status_code=400,
                detail="question_code is required"
            )

        conn = await get_db()

        print("==========================================")
        print("📥 RESPONSE RECEIVED")
        print("Session ID    :", data.session_id)
        print("Question Code :", data.question_code)
        print("Selected      :", data.selected_option)
        print("Text          :", data.text_response)
        print("==========================================")

        # ----------------------------------------------------
        # 2. Get session
        # ----------------------------------------------------

        session = await conn.fetchrow(
            """
            SELECT
                session_id,
                user_category
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

        user_category = session["user_category"]

        print("🔎 Session category:", user_category)

        # ----------------------------------------------------
        # 3. A / B are universal questions
        # ----------------------------------------------------

        if data.question_code in ["A", "B"]:

            question = await conn.fetchrow(
                """
                SELECT
                    question_id,
                    question_code,
                    question_type
                FROM questions
                WHERE question_code = $1
                  AND is_active = true
                LIMIT 1
                """,
                data.question_code
            )

            if not question:
                raise HTTPException(
                    status_code=404,
                    detail=f"Universal question not found: {data.question_code}"
                )

            response_type = (
                "choice"
                if data.selected_option
                else "text"
            )

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

            print("✅ Universal response saved:", data.question_code)
            print("Response ID:", response_id)

            return {
                "success": True,
                "response_id": str(response_id),
                "session_id": data.session_id,
                "question_code": data.question_code
            }

        # ----------------------------------------------------
        # 4. Q1-Q10 require category
        # ----------------------------------------------------

        if not user_category:

            raise HTTPException(
                status_code=400,
                detail="Session category has not been set"
            )

        # ----------------------------------------------------
        # 5. Validate category
        # ----------------------------------------------------

        valid_categories = [
            "fresher",
            "senior",
            "manager",
            "transition",
            "business",
            "student",
            "undecided"
        ]

        if user_category not in valid_categories:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid session category: '{user_category}'. "
                    f"Expected one of: {', '.join(valid_categories)}"
                )
            )

        # ----------------------------------------------------
        # 6. Find category question
        # ----------------------------------------------------

        category_question = await conn.fetchrow(
            """
            SELECT
                category_question_id,
                category_code,
                question_number,
                question_text,
                is_voice
            FROM category_questions
            WHERE category_code = $1
              AND question_number = $2
            LIMIT 1
            """,
            user_category,
            data.question_code
        )

        if not category_question:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Question {data.question_code} not found "
                    f"for category {user_category}"
                )
            )

        # ----------------------------------------------------
        # 7. Determine response type
        # ----------------------------------------------------

        if category_question["is_voice"]:

            response_type = "voice"

        elif data.selected_option:

            response_type = "choice"

        elif data.text_response:

            response_type = "text"

        else:

            response_type = "unknown"

        # ----------------------------------------------------
        # 8. Save category response
        # ----------------------------------------------------

        response_id = await conn.fetchval(
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
            RETURNING response_id
            """,
            data.session_id,
            category_question["category_question_id"],
            data.selected_option,
            data.text_response,
            response_type
        )

        print("==========================================")
        print("✅ CATEGORY RESPONSE SAVED")
        print("Session ID          :", data.session_id)
        print("Category            :", user_category)
        print("Question Code       :", data.question_code)
        print("Category Question ID:", category_question["category_question_id"])
        print("Response Type       :", response_type)
        print("Response ID         :", response_id)
        print("==========================================")

        return {
            "success": True,
            "response_id": str(response_id),
            "session_id": data.session_id,
            "question_code": data.question_code,
            "category": user_category
        }

    except HTTPException:
        raise

    except Exception as e:

        print("==========================================")
        print("❌ RESPONSE SAVE ERROR")
        print("Error type:", type(e).__name__)
        print("Error:", str(e))
        print("==========================================")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()

# ============================================================
# VOICE ANALYSIS - WITH GEMINI AI
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

        session = await conn.fetchrow(
            """
            SELECT
                session_id,
                user_category
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

        category = session["user_category"]

        # FIND CATEGORY VOICE QUESTION
        category_question = await conn.fetchrow(
            """
            SELECT
                category_question_id
            FROM category_questions
            WHERE category_code = $1
            AND question_number = $2
            AND is_voice = true
            LIMIT 1
            """,
            category,
            data.question_code
        )

        if not category_question:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Voice question {data.question_code} "
                    f"not found for category {category}"
                )
            )

        # SAVE TRANSCRIPT
        response_id = await conn.fetchval(
            """
            INSERT INTO responses
            (
                session_id,
                category_question_id,
                response_type,
                text_response
            )
            VALUES
            (
                $1,
                $2,
                'voice',
                $3
            )
            RETURNING response_id
            """,
            data.session_id,
            category_question[
                "category_question_id"
            ],
            data.transcript
        )

        # ✅ ANALYZE WITH GEMINI AI
        analysis = await analyze_voice_with_gemini(
            transcript=data.transcript,
            user_category=category,
            question_code=data.question_code
        )

        # ✅ SAVE AI ANALYSIS RESULTS
        await conn.execute(
            """
            INSERT INTO voice_analysis
            (
                response_id,
                session_id,
                ai_persona_code,
                ai_persona_name,
                ai_comments,
                ai_confidence,
                ai_analysis_timestamp
            )
            VALUES
            (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                NOW()
            )
            """,
            response_id,
            data.session_id,
            analysis.get("persona_code"),
            analysis.get("persona_name"),
            json.dumps(analysis.get("comments", [])),
            analysis.get("confidence", 70)
        )

        print("🎙️ VOICE RESPONSE SAVED WITH AI ANALYSIS")
        print("Session:", data.session_id)
        print("Question:", data.question_code)
        print("Response:", response_id)
        print("AI Persona:", analysis.get("persona_name"))

        return {
            "success": True,
            "response_id": str(response_id),
            "analysis": analysis
        }

    except HTTPException:
        raise
    except Exception as e:
        print("❌ VOICE ANALYSIS ERROR:", e)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()


# ============================================================
# GEMINI AI VOICE ANALYSIS FUNCTION
# ============================================================

async def analyze_voice_with_gemini(transcript: str, user_category: str, question_code: str):
    """
    Analyze voice transcript using Google Gemini AI
    Returns: persona_code, persona_name, comments, confidence
    """
    try:
        # Get the Gemini model
        model = genai.GenerativeModel('gemini-pro')
        
        # List of 12 personas for AI to choose from
        persona_list = """
        1. The Translator (TRANS) - Makes complex things simple, high emotional intelligence
        2. The Amplifier (AMP) - Clear presence, impactful delivery
        3. The Articulator (ART) - Explains clearly, provides depth
        4. The Interpreter (INTERP) - Translates ideas, but loses nuance
        5. The Filter (FILTER) - Valuable insights, but overloads with information
        6. The Mumbler (MUMBLE) - Good thoughts, unclear delivery
        7. The Eclipsed (ECLIPSE) - Good ideas, overlooked by others
        8. The Unheard (UNHEARD) - Honest but not connecting
        9. The Overlooked (OVERLOOK) - Consistent but invisible
        10. The Faded (FADED) - Strong start, loses momentum
        11. The Ghost (GHOST) - Present but not heard
        12. The Disconnected (DISCON) - Significant gap between thinking and speaking
        """
        
        prompt = f"""
        You are a communication expert analyzing a user's voice response.
        
        User Category: {user_category}
        Question Code: {question_code}
        
        User's Transcript: "{transcript}"
        
        Based on this transcript, please:
        
        1. Identify which of the 12 personas best matches this user:
        {persona_list}
        
        2. Provide 2-3 specific, actionable comments about their communication style based on what they said.
        
        Return ONLY valid JSON in this exact format:
        {{
            "persona_code": "ART",
            "persona_name": "The Articulator",
            "comments": [
                "You clearly explained the concept using relatable examples, which shows strong clarity.",
                "Your enthusiasm made the topic engaging, though you could benefit from more structure."
            ],
            "confidence": 85
        }}
        
        Persona codes are: TRANS, AMP, ART, INTERP, FILTER, MUMBLE, ECLIPSE, UNHEARD, OVERLOOK, FADED, GHOST, DISCON
        """
        
        # Call Gemini AI
        response = model.generate_content(prompt)
        result = response.text
        
        # Parse JSON from AI response
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            # Fallback if JSON parsing fails
            analysis = {
                "persona_code": "ART",
                "persona_name": "The Articulator",
                "comments": [
                    "Your response shows good effort in explaining the topic.",
                    "Consider adding more structure to your delivery."
                ],
                "confidence": 70
            }
        
        # Validate persona_code exists in our list
        valid_personas = ["TRANS", "AMP", "ART", "INTERP", "FILTER", "MUMBLE", 
                         "ECLIPSE", "UNHEARD", "OVERLOOK", "FADED", "GHOST", "DISCON"]
        
        if analysis.get("persona_code") not in valid_personas:
            analysis["persona_code"] = "ART"
            analysis["persona_name"] = "The Articulator"
        
        return analysis
        
    except Exception as e:
        print(f"❌ Gemini AI analysis error: {e}")
        # Return fallback analysis
        return {
            "persona_code": "ART",
            "persona_name": "The Articulator",
            "comments": [
                "Your response shows genuine effort in communicating your thoughts.",
                "Keep practicing to develop more clarity and confidence in your delivery."
            ],
            "confidence": 65
        }


# ============================================================
# COMPLETE ASSESSMENT
# ============================================================

@app.post("/api/assessment/complete")
async def complete_assessment(
    data: AssessmentCompleteRequest
):

    conn = None

    try:

        if not data.session_id:

            raise HTTPException(
                status_code=400,
                detail="Session ID is required"
            )

        conn = await get_db()

        # ----------------------------------------------------
        # SESSION
        # ----------------------------------------------------

        session = await conn.fetchrow(
            """
            SELECT
                session_id,
                user_id,
                user_category,
                status
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

        user_id = session["user_id"]

        # ----------------------------------------------------
        # USER DETAILS
        # ----------------------------------------------------

        if data.user_details and data.user_details.email:

            existing_user = await conn.fetchrow(
                """
                SELECT user_id
                FROM users
                WHERE email = $1
                LIMIT 1
                """,
                data.user_details.email
            )

            if existing_user:

                user_id = existing_user["user_id"]

            else:

                user_id = await conn.fetchval(
                    """
                    INSERT INTO users
                    (
                        full_name,
                        email,
                        phone
                    )
                    VALUES
                    (
                        $1,
                        $2,
                        $3
                    )
                    RETURNING user_id
                    """,
                    data.user_details.full_name,
                    data.user_details.email,
                    data.user_details.phone
                )

            await conn.execute(
                """
                UPDATE assessment_sessions
                SET user_id = $1
                WHERE session_id = $2
                """,
                user_id,
                data.session_id
            )

        # ----------------------------------------------------
        # GET ALL RESPONSES
        # ----------------------------------------------------

        responses = await conn.fetch(
            """
            SELECT
                r.response_id,
                r.selected_option,
                r.text_response,
                r.response_type,
                q.question_code AS universal_question_code,
                cq.question_number AS category_question_code
            FROM responses r

            LEFT JOIN questions q
                ON r.question_id = q.question_id

            LEFT JOIN category_questions cq
                ON r.category_question_id =
                   cq.category_question_id

            WHERE r.session_id = $1

            ORDER BY r.created_at
            """,
            data.session_id
        )

        # ----------------------------------------------------
        # BASIC SCORE
        # ----------------------------------------------------

        scores = {
            "SIM": 0,
            "PER": 0,
            "THI": 0,
            "CUR": 0,
            "PRE": 0,
            "CON": 0,
            "EMV": 0
        }

        for response in responses:

            selected = response["selected_option"]

            if not selected:
                continue

            code = (
                response["category_question_code"]
                or response["universal_question_code"]
            )

            if code and str(code).startswith("Q"):

                scores["SIM"] += 1

            else:

                scores["PER"] += 1

        top_archetype = max(
            scores,
            key=scores.get
        )

        # ----------------------------------------------------
        # ARCHETYPE
        # ----------------------------------------------------

        archetype = await conn.fetchrow(
            """
            SELECT
                archetype_code,
                archetype_name,
                description
            FROM archetypes
            WHERE archetype_code = $1
            LIMIT 1
            """,
            top_archetype
        )

        # ----------------------------------------------------
        # SAVE RESULT
        # ----------------------------------------------------

        await conn.execute(
            """
            INSERT INTO assessment_results
            (
                session_id,
                user_id,
                archetype_code,
                overall_score,
                score_breakdown,
                result_text
            )
            VALUES
            (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6
            )
            """,
            data.session_id,
            user_id,
            top_archetype,
            scores[top_archetype],
            json.dumps(scores),
            (
                f"Your primary archetype is "
                f"{archetype['archetype_name']}"
                if archetype
                else
                f"Your primary archetype is "
                f"{top_archetype}"
            )
        )

        # ----------------------------------------------------
        # COMPLETE SESSION
        # ----------------------------------------------------

        await conn.execute(
            """
            UPDATE assessment_sessions
            SET
                status = 'completed',
                completed_at = NOW()
            WHERE session_id = $1
            """,
            data.session_id
        )

        return {

            "success": True,

            "session_id":
                data.session_id,

            "user_id":
                user_id,

            "archetype_code":
                top_archetype,

            "archetype_name":
                archetype["archetype_name"]
                if archetype
                else top_archetype,

            "archetype_description":
                archetype["description"]
                if archetype
                else "",

            "scores":
                scores,

            "overall_score":
                scores[top_archetype]

        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ ASSESSMENT COMPLETE ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


# ============================================================
# GET ASSESSMENT RESULT
# ============================================================

@app.get("/api/assessment/result/{session_id}")
async def get_assessment_result(session_id: str):

    conn = None

    try:

        conn = await get_db()

        session = await conn.fetchrow(
            """
            SELECT
                session_id,
                user_id,
                status
            FROM assessment_sessions
            WHERE session_id = $1
            """,
            session_id
        )

        if not session:

            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        if session["status"] != "completed":

            raise HTTPException(
                status_code=400,
                detail="Assessment not completed yet"
            )

        result = await conn.fetchrow(
            """
            SELECT
                archetype_code,
                overall_score,
                score_breakdown,
                result_text,
                created_at
            FROM assessment_results
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            session_id
        )

        if not result:

            raise HTTPException(
                status_code=404,
                detail="Result not found"
            )

        archetype = await conn.fetchrow(
            """
            SELECT
                archetype_code,
                archetype_name,
                description
            FROM archetypes
            WHERE archetype_code = $1
            LIMIT 1
            """,
            result["archetype_code"]
        )

        return {

            "success": True,

            "session_id":
                session_id,

            "user_id":
                session["user_id"],

            "status":
                session["status"],

            "archetype": {

                "code":
                    archetype["archetype_code"],

                "name":
                    archetype["archetype_name"],

                "description":
                    archetype["description"]

            } if archetype else None,

            "overall_score":
                result["overall_score"],

            "score_breakdown":
                result["score_breakdown"],

            "result_text":
                result["result_text"],

            "completed_at":
                result["created_at"]

        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ RESULT ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

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
            """
            SELECT
                archetype_id,
                archetype_code,
                archetype_name,
                description,
                key_traits,
                strengths,
                growth_areas,
                communication_style
            FROM archetypes
            ORDER BY archetype_id
            """
        )

        return {
            "success": True,
            "archetypes": [
                dict(row)
                for row in rows
            ]
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


# ============================================================
# GENERATE FREE REPORT - WITH VOICE PERSONA
# ============================================================
@app.post("/api/report/generate-free")
async def generate_free_report(data: dict):
    conn = None
    try:
        print("=" * 50)
        print("📝 GENERATE FREE REPORT")
        
        session_id = data.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID required")
        
        print(f"🔍 Session ID: {session_id}")
        conn = await get_db()
        
        # Get session with user details
        session = await conn.fetchrow(
            """SELECT s.session_id, s.user_id, s.user_category, s.status,
                      u.full_name, u.email
               FROM assessment_sessions s
               LEFT JOIN users u ON s.user_id = u.user_id
               WHERE s.session_id = $1""",
            session_id
        )
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session["status"] != "completed":
            raise HTTPException(status_code=400, detail="Assessment not completed yet")
        
        user_name = session["full_name"] or "Professional"
        print(f"✅ User: {user_name}")
        print(f"✅ Status: {session['status']}")
        print(f"✅ Category: {session['user_category']}")
        
        # Get archetype from assessment_results
        result = await conn.fetchrow(
            """SELECT archetype_code, overall_score
               FROM assessment_results
               WHERE session_id = $1
               ORDER BY created_at DESC
               LIMIT 1""",
            session_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="No results found")
        
        archetype_code = result["archetype_code"]
        print(f"✅ Archetype: {archetype_code}")
        
        # ✅ GET AI VOICE PERSONA (if available)
        voice_analysis = await conn.fetchrow(
            """SELECT ai_persona_code, ai_persona_name, ai_comments, ai_confidence
               FROM voice_analysis
               WHERE session_id = $1
               ORDER BY ai_analysis_timestamp DESC
               LIMIT 1""",
            session_id
        )
        
        if voice_analysis:
            print(f"✅ Voice Persona: {voice_analysis['ai_persona_name']} (Confidence: {voice_analysis['ai_confidence']}%)")
        
        # Get responses
        responses = await conn.fetch(
            """
            SELECT 
                r.selected_option,
                r.text_response,
                r.response_type,
                q.question_code as universal_code,
                cq.question_number as category_code
            FROM responses r
            LEFT JOIN questions q ON r.question_id = q.question_id
            LEFT JOIN category_questions cq ON r.category_question_id = cq.category_question_id
            WHERE r.session_id = $1
            """,
            session_id
        )
        
        print(f"✅ Found {len(responses)} responses")
        
        # Calculate DNA scores
        dna_scores = {
            "thinking": 0,
            "structure": 0,
            "expression": 0,
            "understanding": 0,
            "influence": 0
        }
        
        dimension_mapping = {
            "Q1": "thinking", "Q2": "structure", "Q3": "thinking",
            "Q4": "structure", "Q5": "understanding", "Q6": "influence",
            "Q7": "thinking", "Q8": "expression", "Q9": "understanding",
            "Q10": "influence"
        }
        
        for r in responses:
            code = r["universal_code"] or r["category_code"]
            if code in ["A", "B"]:
                continue
            if code and code in dimension_mapping:
                dimension = dimension_mapping[code]
                selected = r["selected_option"]
                if selected:
                    if selected in ['A', 'a']:
                        dna_scores[dimension] += 4
                    elif selected in ['B', 'b']:
                        dna_scores[dimension] += 3
                    elif selected in ['C', 'c']:
                        dna_scores[dimension] += 2
                    elif selected in ['D', 'd']:
                        dna_scores[dimension] += 1
                    elif r["response_type"] == "voice" and r["text_response"]:
                        word_count = len(r["text_response"].split())
                        if word_count > 20:
                            dna_scores[dimension] += 3
                        elif word_count > 10:
                            dna_scores[dimension] += 2
                        else:
                            dna_scores[dimension] += 1
        
        max_score = 20
        for key in dna_scores:
            dna_scores[key] = min(round((dna_scores[key] / max_score) * 100), 100)
            if dna_scores[key] < 10:
                dna_scores[key] = 10
        
        print(f"✅ DNA Scores: {dna_scores}")
        
        # Determine which persona to use
        assessment_persona = await conn.fetchrow(
            """SELECT * FROM personas WHERE archetype_code = $1 LIMIT 1""",
            archetype_code
        )
        
        if not assessment_persona:
            assessment_persona = await conn.fetchrow(
                "SELECT * FROM personas WHERE persona_code = 'ART'"
            )
        
        primary_persona = assessment_persona
        persona_source = "Assessment"
        
        # Use AI persona if confidence > 70%
        if voice_analysis and voice_analysis["ai_confidence"] and voice_analysis["ai_confidence"] > 70:
            ai_persona = await conn.fetchrow(
                "SELECT * FROM personas WHERE persona_code = $1",
                voice_analysis["ai_persona_code"]
            )
            if ai_persona:
                primary_persona = ai_persona
                persona_source = "AI Voice Analysis"
                print(f"✅ Using AI Persona: {primary_persona['persona_name']}")
        
        # Build report
        report_data = {
            "user_name": user_name,
            "persona_code": primary_persona["persona_code"],
            "persona_name": primary_persona["persona_name"],
            "refined_description": primary_persona["refined_description"],
            "you_tend_to": primary_persona["you_tend_to"],
            "you_naturally_bring": primary_persona["you_naturally_bring"],
            "you_may_create": primary_persona["you_may_create"],
            "greatest_advantage": primary_persona["greatest_advantage"],
            "biggest_risk": primary_persona["biggest_risk"],
            "natural_advantage": primary_persona["natural_advantage"],
            "blind_spot": primary_persona["blind_spot"],
            "blind_spot_description": primary_persona["blind_spot_description"],
            "communication_dna": dna_scores,
            "unspoken_gap": "Intention → Expression → Experience",
            "voice_analysis": {
                "persona_code": voice_analysis["ai_persona_code"] if voice_analysis else None,
                "persona_name": voice_analysis["ai_persona_name"] if voice_analysis else None,
                "comments": voice_analysis["ai_comments"] if voice_analysis else [],
                "confidence": voice_analysis["ai_confidence"] if voice_analysis else 0
            } if voice_analysis else None,
            "persona_source": persona_source
        }
        
        print("=" * 50)
        
        return {
            "success": True,
            "report": report_data
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# HELPER: GET BEST PERSONA
# ============================================================

async def get_best_persona(conn, archetype_code, dna_scores):
    """
    Find the best matching persona based on archetype and DNA scores.
    """
    # First, get all personas for this archetype
    personas = await conn.fetch(
        """SELECT * FROM personas 
           WHERE archetype_code = $1 
           ORDER BY persona_id""",
        archetype_code
    )
    
    if not personas:
        return None
    
    # If only one persona for this archetype, return it
    if len(personas) == 1:
        return personas[0]
    
    # Calculate which persona matches best based on scores
    best_match = None
    best_score = -1
    
    for persona in personas:
        # Simple matching logic - you can make this more sophisticated
        # For now, return the first one for the archetype
        if best_match is None:
            best_match = persona
    
    return best_match


# ============================================================
# HELPER: CALCULATE COMMUNICATION DNA
# ============================================================

def calculate_communication_dna(responses, user_category):
    """
    Calculate the 5 DNA scores based on user responses.
    """
    # Initialize scores
    dna_scores = {
        "thinking": 0,
        "structure": 0,
        "expression": 0,
        "understanding": 0,
        "influence": 0
    }
    
    # Question to dimension mapping
    dimension_mapping = {
        "Q1": "thinking",
        "Q2": "structure",
        "Q3": "thinking",
        "Q4": "structure",
        "Q5": "understanding",
        "Q6": "influence",
        "Q7": "thinking",
        "Q8": "expression",
        "Q9": "understanding",
        "Q10": "influence"
    }
    
    # Process each response
    for response in responses:
        question_code = response.get("question_code")
        selected_option = response.get("selected_option")
        
        if question_code in dimension_mapping:
            dimension = dimension_mapping[question_code]
            
            # Score based on option (A=4, B=3, C=2, D=1, E=0.5)
            option_score = 0
            if selected_option in ['A', 'a']:
                option_score = 4
            elif selected_option in ['B', 'b']:
                option_score = 3
            elif selected_option in ['C', 'c']:
                option_score = 2
            elif selected_option in ['D', 'd']:
                option_score = 1
            elif selected_option in ['E', 'e']:
                option_score = 0.5
            
            dna_scores[dimension] += option_score
    
    # Normalize to 0-100
    max_score = 20  # 5 questions × 4 points each
    for dimension in dna_scores:
        dna_scores[dimension] = min(round((dna_scores[dimension] / max_score) * 100), 100)
        # Ensure minimum score is 10
        if dna_scores[dimension] < 10:
            dna_scores[dimension] = 10
    
    return dna_scores
