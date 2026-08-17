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

        await conn.execute(
            """
            UPDATE assessment_sessions
            SET user_category = $1
            WHERE session_id = $2
            """,
            data.user_category,
            session_id
        )

        print(
            f"✅ Category set: {data.user_category}"
        )

        return {
            "success": True,
            "session_id": session_id,
            "user_category": data.user_category
        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ Category error:", e)

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
# SAVE RESPONSE
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
        # VERIFY SESSION
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

        # ----------------------------------------------------
        # A / B UNIVERSAL QUESTIONS
        # ----------------------------------------------------

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

        if question:

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
                VALUES
                (
                    $1,
                    $2,
                    $3,
                    $4,
                    $5
                )
                RETURNING response_id
                """,
                data.session_id,
                question["question_id"],
                data.selected_option,
                data.text_response,
                response_type
            )

        # ----------------------------------------------------
        # CATEGORY Q1-Q10
        # ----------------------------------------------------

        else:

            category = session["user_category"]

            if not category:

                raise HTTPException(
                    status_code=400,
                    detail="Session category has not been set"
                )

            category_question = await conn.fetchrow(
                """
                SELECT
                    category_question_id,
                    question_number,
                    is_voice
                FROM category_questions
                WHERE category_code = $1
                AND question_number = $2
                LIMIT 1
                """,
                category,
                data.question_code
            )

            if not category_question:

                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Question {data.question_code} "
                        f"not found for category {category}"
                    )
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
                VALUES
                (
                    $1,
                    $2,
                    $3,
                    $4,
                    $5
                )
                RETURNING response_id
                """,
                data.session_id,
                category_question[
                    "category_question_id"
                ],
                data.selected_option,
                data.text_response,
                response_type
            )

        print("==========================================")
        print("✅ RESPONSE SAVED")
        print("Session       :", data.session_id)
        print("Question      :", data.question_code)
        print("Selected      :", data.selected_option)
        print("Response ID   :", response_id)
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

        # ----------------------------------------------------
        # FIND CATEGORY VOICE QUESTION
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # SAVE TRANSCRIPT
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # TEMPORARY ANALYSIS
        # ----------------------------------------------------

        analysis = {

            "clarity": 70,
            "structure": 65,
            "confidence": 75,
            "presence": 70,
            "connection": 68,
            "influence": 72,
            "overall": 70,

            "feedback":
                "Good communication skills with room for improvement."

        }

        # ----------------------------------------------------
        # SAVE ANALYSIS
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
            VALUES
            (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9
            )
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

        print("🎙️ VOICE RESPONSE SAVED")
        print("Session:", data.session_id)
        print("Question:", data.question_code)
        print("Response:", response_id)

        return {
            "success": True,
            "response_id": str(response_id),
            "analysis": analysis
        }

    except HTTPException:
        raise

    except Exception as e:

        print("❌ VOICE ANALYSIS ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:

        if conn:
            await conn.close()


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
        #
        # IMPORTANT:
        # A/B use question_id
        # Q1-Q10 use category_question_id
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

        print(
            f"📊 Found {len(responses)} responses "
            f"for session {data.session_id}"
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

            # Temporary scoring.
            # Replace with your real scoring engine later.

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
