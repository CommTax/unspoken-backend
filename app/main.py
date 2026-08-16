from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional
from pydantic import BaseModel

from app.routes import analyze

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
    return await asyncpg.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        database=os.environ.get('DB_NAME', 'theunspoken_db'),
        user=os.environ.get('DB_USER', 'theunspoken_user'),
        password=os.environ.get('DB_PASSWORD', ''),
        port=os.environ.get('DB_PORT', '5432'),
        sslmode='require'  # Add this line
    )

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
    return {"service": "Unspoken Backend", "status": "running", "docs": "/docs"}

# ============================================================
# HEALTH CHECK (with database connection test)
# ============================================================
@app.get("/api/health")
async def health():
    try:
        conn = await get_db()
        result = await conn.fetch("SELECT NOW()")
        await conn.close()
        return {
            "status": "✅ API is running!",
            "database": "Connected",
            "timestamp": result[0]['now']
        }
    except Exception as e:
        return {
            "status": "⚠️ API running but database connection failed",
            "error": str(e)
        }

# ============================================================
# USERS ROUTES
# ============================================================
@app.post("/api/users")
async def create_user(user: UserCreate):
    try:
        conn = await get_db()
        result = await conn.fetch(
            """INSERT INTO users (full_name, email, whatsapp) 
               VALUES ($1, $2, $3) 
               RETURNING user_id, full_name, email, whatsapp, created_at""",
            user.fullName, user.email, user.whatsapp
        )
        await conn.close()
        
        return {
            "success": True,
            "user": {
                "user_id": result[0]['user_id'],
                "full_name": result[0]['full_name'],
                "email": result[0]['email'],
                "whatsapp": result[0]['whatsapp'],
                "created_at": result[0]['created_at']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    try:
        conn = await get_db()
        result = await conn.fetch(
            """SELECT user_id, full_name, email, whatsapp, created_at, assessment_completed, communication_persona 
               FROM users WHERE user_id = $1""",
            user_id
        )
        await conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "success": True,
            "user": {
                "user_id": result[0]['user_id'],
                "full_name": result[0]['full_name'],
                "email": result[0]['email'],
                "whatsapp": result[0]['whatsapp'],
                "created_at": result[0]['created_at'],
                "assessment_completed": result[0]['assessment_completed'],
                "communication_persona": result[0]['communication_persona']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/users/{user_id}")
async def update_user(user_id: str, user: UserCreate):
    try:
        conn = await get_db()
        result = await conn.fetch(
            """UPDATE users 
               SET full_name = COALESCE($1, full_name),
                   email = COALESCE($2, email),
                   whatsapp = COALESCE($3, whatsapp),
                   last_active = CURRENT_TIMESTAMP
               WHERE user_id = $4
               RETURNING user_id, full_name, email, whatsapp""",
            user.fullName, user.email, user.whatsapp, user_id
        )
        await conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "success": True,
            "user": {
                "user_id": result[0]['user_id'],
                "full_name": result[0]['full_name'],
                "email": result[0]['email'],
                "whatsapp": result[0]['whatsapp']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# QUESTIONS ROUTES
# ============================================================
@app.get("/api/questions")
async def get_questions():
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT question_id, question_text, question_type, category, options, display_order 
               FROM questions 
               WHERE is_active = true 
               ORDER BY display_order ASC"""
        )
        await conn.close()
        
        questions = []
        for row in rows:
            questions.append({
                "question_id": row['question_id'],
                "question_text": row['question_text'],
                "question_type": row['question_type'],
                "category": row['category'],
                "options": row['options'],
                "display_order": row['display_order']
            })
        
        return {
            "success": True,
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/questions/category/{category}")
async def get_questions_by_category(category: str):
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT question_id, question_text, question_type, options, display_order 
               FROM questions 
               WHERE category = $1 AND is_active = true 
               ORDER BY display_order ASC""",
            category
        )
        await conn.close()
        
        questions = []
        for row in rows:
            questions.append({
                "question_id": row['question_id'],
                "question_text": row['question_text'],
                "question_type": row['question_type'],
                "options": row['options'],
                "display_order": row['display_order']
            })
        
        return {
            "success": True,
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# RESPONSES ROUTES
# ============================================================
@app.post("/api/responses")
async def submit_response(response: ResponseSubmit):
    try:
        conn = await get_db()
        result = await conn.fetch(
            """INSERT INTO responses (user_id, question_id, answer, response_type, voice_url) 
               VALUES ($1, $2, $3, $4, $5) 
               RETURNING response_id, created_at""",
            response.userId, response.questionId, response.answer, 
            response.responseType, response.voiceUrl
        )
        await conn.close()
        
        return {
            "success": True,
            "response": {
                "response_id": result[0]['response_id'],
                "created_at": result[0]['created_at']
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/responses/user/{user_id}")
async def get_user_responses(user_id: str):
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT r.*, q.question_text, q.category 
               FROM responses r
               JOIN questions q ON r.question_id = q.question_id
               WHERE r.user_id = $1 
               ORDER BY r.created_at ASC""",
            user_id
        )
        await conn.close()
        
        responses = []
        for row in rows:
            responses.append(dict(row))
        
        return {
            "success": True,
            "responses": responses
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ARCHETYPE ROUTES
# ============================================================
@app.get("/api/archetypes")
async def get_archetypes():
    try:
        conn = await get_db()
        rows = await conn.fetch(
            """SELECT archetype_id, archetype_name, archetype_code, description, key_traits, strengths, growth_areas, communication_style 
               FROM archetypes 
               ORDER BY archetype_id"""
        )
        await conn.close()
        
        archetypes = []
        for row in rows:
            archetypes.append({
                "archetype_id": row['archetype_id'],
                "archetype_name": row['archetype_name'],
                "archetype_code": row['archetype_code'],
                "description": row['description'],
                "key_traits": row['key_traits'],
                "strengths": row['strengths'],
                "growth_areas": row['growth_areas'],
                "communication_style": row['communication_style']
            })
        
        return {
            "success": True,
            "archetypes": archetypes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/archetypes/{archetype_id}")
async def get_archetype(archetype_id: int):
    try:
        conn = await get_db()
        row = await conn.fetchrow(
            """SELECT * FROM archetypes WHERE archetype_id = $1""",
            archetype_id
        )
        await conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Archetype not found")
        
        return {
            "success": True,
            "archetype": dict(row)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ASSESSMENT COMPLETION ROUTE
# ============================================================
@app.post("/api/assessment/complete")
async def complete_assessment(data: dict):
    try:
        user_id = data.get('userId')
        responses = data.get('responses', [])
        communication_persona = data.get('communicationPersona')
        archetype_id = data.get('archetypeId')
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required")
        
        conn = await get_db()
        
        # Start transaction
        async with conn.transaction():
            # Insert all responses
            for response in responses:
                await conn.execute(
                    """INSERT INTO responses (user_id, question_id, answer, response_type) 
                       VALUES ($1, $2, $3, $4)""",
                    user_id, response['questionId'], response['answer'], 
                    response.get('responseType', 'choice')
                )
            
            # Update user with assessment results
            await conn.execute(
                """UPDATE users 
                   SET assessment_completed = true,
                       communication_persona = COALESCE($1, communication_persona),
                       archetype_id = COALESCE($2, archetype_id),
                       last_active = CURRENT_TIMESTAMP
                   WHERE user_id = $3""",
                communication_persona, archetype_id, user_id
            )
        
        await conn.close()
        
        return {
            "success": True,
            "message": "Assessment completed successfully",
            "communicationPersona": communication_persona,
            "archetypeId": archetype_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/assessment/result/{user_id}")
async def get_assessment_result(user_id: str):
    try:
        conn = await get_db()
        
        # Get user with assessment results
        user_result = await conn.fetchrow(
            """SELECT user_id, full_name, email, communication_persona, archetype_id, assessment_completed
               FROM users 
               WHERE user_id = $1""",
            user_id
        )
        
        if not user_result:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user_result['assessment_completed']:
            raise HTTPException(status_code=400, detail="Assessment not completed yet")
        
        # Get archetype details if available
        archetype = None
        if user_result['archetype_id']:
            archetype_row = await conn.fetchrow(
                """SELECT * FROM archetypes WHERE archetype_id = $1""",
                user_result['archetype_id']
            )
            if archetype_row:
                archetype = dict(archetype_row)
        
        await conn.close()
        
        return {
            "success": True,
            "result": {
                "user_id": user_result['user_id'],
                "full_name": user_result['full_name'],
                "email": user_result['email'],
                "communication_persona": user_result['communication_persona'],
                "assessment_completed": user_result['assessment_completed'],
                "archetype": archetype
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include your existing analyze router
app.include_router(analyze.router, prefix="/api", tags=["Analysis"])
