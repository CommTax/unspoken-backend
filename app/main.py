from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional
from pydantic import BaseModel
from urllib.parse import urlparse

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

class ResponseSubmit(BaseModel):
    userId: str
    questionId: int
    answer: dict
    responseType: str = "choice"
    voiceUrl: Optional[str] = None

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
        print("❌ HEALTH CHECK FAILED")
        print(f"Error type: {type(e).__name__}")
        print(f"Error: {str(e)}")
        return {
            "status": "⚠️ API running but database connection failed",
            "error_type": type(e).__name__,
            "error": str(e)
        }
    finally:
        if conn:
            await conn.close()

# ============================================================
# USERS ROUTES
# ============================================================
@app.post("/api/users")
async def create_user(user: UserCreate):
    conn = None
    try:
        conn = await get_db()
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

@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetch(
            """
            SELECT user_id, full_name, email, whatsapp, created_at,
                   assessment_completed, communication_persona
            FROM users WHERE user_id = $1
            """,
            user_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "success": True,
            "user": {
                "user_id": result[0]["user_id"],
                "full_name": result[0]["full_name"],
                "email": result[0]["email"],
                "whatsapp": result[0]["whatsapp"],
                "created_at": result[0]["created_at"],
                "assessment_completed": result[0]["assessment_completed"],
                "communication_persona": result[0]["communication_persona"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.put("/api/users/{user_id}")
async def update_user(user_id: str, user: UserCreate):
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# QUESTIONS ROUTES
# ============================================================
@app.get("/api/questions")
async def get_questions():
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """
            SELECT question_id, question_text, question_type, category, options, display_order
            FROM questions WHERE is_active = true ORDER BY display_order ASC
            """
        )
        questions = []
        for row in rows:
            questions.append({
                "question_id": row["question_id"],
                "question_text": row["question_text"],
                "question_type": row["question_type"],
                "category": row["category"],
                "options": row["options"],
                "display_order": row["display_order"]
            })
        return {"success": True, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/questions/category/{category}")
async def get_questions_by_category(category: str):
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """
            SELECT question_id, question_text, question_type, options, display_order
            FROM questions WHERE category = $1 AND is_active = true ORDER BY display_order ASC
            """,
            category
        )
        questions = []
        for row in rows:
            questions.append({
                "question_id": row["question_id"],
                "question_text": row["question_text"],
                "question_type": row["question_type"],
                "options": row["options"],
                "display_order": row["display_order"]
            })
        return {"success": True, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# RESPONSES ROUTES
# ============================================================
@app.post("/api/responses")
async def submit_response(response: ResponseSubmit):
    conn = None
    try:
        conn = await get_db()
        result = await conn.fetch(
            """
            INSERT INTO responses (user_id, question_id, answer, response_type, voice_url)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING response_id, created_at
            """,
            response.userId, response.questionId, response.answer,
            response.responseType, response.voiceUrl
        )
        return {
            "success": True,
            "response": {
                "response_id": result[0]["response_id"],
                "created_at": result[0]["created_at"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/responses/user/{user_id}")
async def get_user_responses(user_id: str):
    conn = None
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """
            SELECT r.*, q.question_text, q.category
            FROM responses r
            JOIN questions q ON r.question_id = q.question_id
            WHERE r.user_id = $1 ORDER BY r.created_at ASC
            """,
            user_id
        )
        return {"success": True, "responses": [dict(row) for row in rows]}
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
            """
            SELECT archetype_id, archetype_name, archetype_code, description,
                   key_traits, strengths, growth_areas, communication_style
            FROM archetypes ORDER BY archetype_id
            """
        )
        archetypes = []
        for row in rows:
            archetypes.append({
                "archetype_id": row["archetype_id"],
                "archetype_name": row["archetype_name"],
                "archetype_code": row["archetype_code"],
                "description": row["description"],
                "key_traits": row["key_traits"],
                "strengths": row["strengths"],
                "growth_areas": row["growth_areas"],
                "communication_style": row["communication_style"]
            })
        return {"success": True, "archetypes": archetypes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

@app.get("/api/archetypes/{archetype_id}")
async def get_archetype(archetype_id: int):
    conn = None
    try:
        conn = await get_db()
        row = await conn.fetchrow(
            "SELECT * FROM archetypes WHERE archetype_id = $1",
            archetype_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Archetype not found")
        return {"success": True, "archetype": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()

# ============================================================
# ASSESSMENT COMPLETION
# ============================================================
@app.post("/api/assessment/complete")
async def complete_assessment(data: dict):
    conn = None
    try:
        user_id = data.get("userId")
        responses = data.get("responses", [])
        communication_persona = data.get("communicationPersona")
        archetype_id = data.get("archetypeId")

        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required")

        conn = await get_db()
        async with conn.transaction():
            for response in responses:
                await conn.execute(
                    """
                    INSERT INTO responses (user_id, question_id, answer, response_type)
                    VALUES ($1, $2, $3, $4)
                    """,
                    user_id,
                    response["questionId"],
                    response["answer"],
                    response.get("responseType", "choice")
                )

            await conn.execute(
                """
                UPDATE users
                SET assessment_completed = true,
                    communication_persona = COALESCE($1, communication_persona),
                    archetype_id = COALESCE($2, archetype_id),
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = $3
                """,
                communication_persona, archetype_id, user_id
            )

        return {
            "success": True,
            "message": "Assessment completed successfully",
            "communicationPersona": communication_persona,
            "archetypeId": archetype_id
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
@app.get("/api/assessment/result/{user_id}")
async def get_assessment_result(user_id: str):
    conn = None
    try:
        conn = await get_db()
        user_result = await conn.fetchrow(
            """
            SELECT user_id, full_name, email, communication_persona, archetype_id, assessment_completed
            FROM users WHERE user_id = $1
            """,
            user_id
        )
        if not user_result:
            raise HTTPException(status_code=404, detail="User not found")
        if not user_result["assessment_completed"]:
            raise HTTPException(status_code=400, detail="Assessment not completed yet")

        archetype = None
        if user_result["archetype_id"]:
            archetype_row = await conn.fetchrow(
                "SELECT * FROM archetypes WHERE archetype_id = $1",
                user_result["archetype_id"]
            )
            if archetype_row:
                archetype = dict(archetype_row)

        return {
            "success": True,
            "result": {
                "user_id": user_result["user_id"],
                "full_name": user_result["full_name"],
                "email": user_result["email"],
                "communication_persona": user_result["communication_persona"],
                "assessment_completed": user_result["assessment_completed"],
                "archetype": archetype
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            await conn.close()
