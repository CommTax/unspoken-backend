# app/routes/questions.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import asyncpg

from app.config import Config

router = APIRouter()


@router.get("")
async def get_questions(
    sprint: str = Query(..., description="interview, gd, leadership, storytelling, charisma"),
    day: Optional[int] = Query(None),
    limit: int = Query(200, le=500),
):
    if sprint not in ("interview", "gd", "leadership", "storytelling", "charisma"):
        raise HTTPException(status_code=400, detail="Invalid sprint type")

    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        if day is not None:
            rows = await conn.fetch(
                """
                SELECT id, sprint, text, focus, target_seconds, difficulty, day_number
                FROM question_bank
                WHERE sprint = $1 AND day_number = $2
                ORDER BY id ASC
                """,
                sprint, day,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, sprint, text, focus, target_seconds, difficulty, day_number
                FROM question_bank
                WHERE sprint = $1
                ORDER BY day_number ASC, id ASC
                LIMIT $2
                """,
                sprint, limit,
            )
        return {"sprint": sprint, "day": day, "count": len(rows), "questions": [dict(r) for r in rows]}
    finally:
        await conn.close()


@router.post("/seed")
async def seed_questions(force: bool = Query(False)):
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        existing = await conn.fetchval("SELECT COUNT(*) FROM question_bank")
        if existing > 0 and not force:
            return {"status": "already_seeded", "count": existing}

        if force and existing > 0:
            await conn.execute("TRUNCATE TABLE question_bank RESTART IDENTITY")

        from app.routes._seed_data import SEED_QUESTIONS

        await conn.executemany(
            """
            INSERT INTO question_bank (sprint, text, focus, target_seconds, difficulty, day_number)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            SEED_QUESTIONS,
        )
        return {"status": "seeded", "count": len(SEED_QUESTIONS)}
    finally:
        await conn.close()
