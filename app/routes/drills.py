# app/routes/drills.py
"""
Drill upload, capture, and analyze endpoints.
Bridges the landing page → product page handoff via one-time JWT sessions.
"""

import os
import json
import uuid
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Depends
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError

from app.services.db import get_conn, dict_cursor
from app.services.r2_client import upload_to_r2, download_from_r2
from app.services.gemini_client import GEMINI_API_KEY, call_gemini_api
from app.services.voice import transcribe_audio  # see below — create if missing


router = APIRouter()

# ─── CONFIG ───
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-env")
JWT_ALGO = "HS256"
JWT_EXPIRES_MIN = int(os.getenv("JWT_EXPIRES_MINUTES", "10"))


# ─── HELPERS ───
def issue_token(email: str, drill_id: str) -> tuple[str, str]:
    """Returns (jti, signed_token)."""
    jti = str(uuid.uuid4())
    now = datetime.utcnow()
    payload = {
        "sub": email,
        "drill_id": str(drill_id),
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRES_MIN),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return jti, token


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.replace("Bearer ", "").strip()


# ─── MODELS ───
class CapturePayload(BaseModel):
    drill_id: str
    name: str
    email: EmailStr
    stage: str
    question_type: Optional[str] = "intro"
    mode: Optional[str] = "voice"


# ============================================================
# POST /api/drills/upload
# ============================================================
@router.post("/upload")
async def upload_drill(
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    question_type: str = Form("intro"),
    mode: str = Form("voice"),
    duration_seconds: int = Form(30),
):
    if mode == "voice" and not audio:
        raise HTTPException(400, "audio file required for voice mode")
    if mode == "text" and not text:
        raise HTTPException(400, "text required for text mode")

    drill_id = str(uuid.uuid4())
    audio_url = None

    # Upload audio to R2 (if voice)
    if mode == "voice" and audio:
        try:
            content = await audio.read()
            key = f"drills/{drill_id}.webm"
            audio_url = upload_to_r2(key, content, content_type="audio/webm")
        except Exception as e:
            raise HTTPException(500, f"R2 upload failed: {e}")

    # Insert drill row
    conn = get_conn()
    try:
        with dict_cursor(conn) as cur:
            cur.execute("""
                INSERT INTO free_drills
                  (drill_id, status, mode, question_type, audio_url, duration_seconds, raw_text)
                VALUES (%s, 'uploaded', %s, %s, %s, %s, %s)
            """, (drill_id, mode, question_type, audio_url, duration_seconds, text))
    finally:
        conn.close()

    return {"drill_id": drill_id, "status": "uploaded"}


# ============================================================
# POST /api/drills/capture
# ============================================================
@router.post("/capture")
def capture_lead(payload: CapturePayload):
    conn = get_conn()
    try:
        with dict_cursor(conn) as cur:
            # Verify drill exists
            cur.execute("SELECT drill_id FROM free_drills WHERE drill_id = %s", (payload.drill_id,))
            if not cur.fetchone():
                raise HTTPException(404, "drill_id not found")

            # Link drill to email
            cur.execute("""
                UPDATE free_drills SET email = %s WHERE drill_id = %s
            """, (payload.email, payload.drill_id))

            # Upsert into user_sessions (creates the trial session)
            cur.execute("""
                INSERT INTO user_sessions (email, name, stage, plan, current_day, total_days,
                                           questions_per_day, trials_per_question)
                VALUES (%s, %s, %s, 'trial', 1, 28, 2, 2)
                ON CONFLICT (email) DO UPDATE SET
                  name = EXCLUDED.name,
                  stage = EXCLUDED.stage,
                  updated_at = NOW()
            """, (payload.email, payload.name, payload.stage))

            # Issue one-time-use token
            jti, token = issue_token(payload.email, payload.drill_id)
            expires_at = datetime.utcnow() + timedelta(minutes=JWT_EXPIRES_MIN)
            cur.execute("""
                INSERT INTO session_tokens (jti, email, drill_id, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (jti, payload.email, payload.drill_id, expires_at))

    finally:
        conn.close()

    return {
        "user_id": payload.email,
        "session_token": token,
        "expires_in": JWT_EXPIRES_MIN * 60,
        "drill_id": payload.drill_id,
    }


# ============================================================
# POST /api/drills/analyze
# ============================================================
@router.post("/analyze")
def analyze_drill(token: str = Depends(bearer_token)):
    # Verify JWT
    claims = verify_token(token)
    jti = claims["jti"]
    email = claims["sub"]
    drill_id = claims["drill_id"]

    conn = get_conn()
    try:
        with dict_cursor(conn) as cur:
            # Check token not used
            cur.execute("SELECT used_at, expires_at FROM session_tokens WHERE jti = %s", (jti,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(401, "Token not found")
            if row["used_at"] is not None:
                raise HTTPException(401, "Token already used")
            if row["expires_at"] < datetime.utcnow():
                raise HTTPException(401, "Token expired")

            # Load drill
            cur.execute("""
                SELECT d.*, s.name, s.stage
                FROM free_drills d
                LEFT JOIN user_sessions s ON s.email = d.email
                WHERE d.drill_id = %s
            """, (drill_id,))
            drill = cur.fetchone()
            if not drill:
                raise HTTPException(404, "Drill not found")

        # ─── Run analysis ───
        try:
            analysis = run_analysis_pipeline(drill)
        except Exception as e:
            with dict_cursor(conn) as cur:
                cur.execute("UPDATE free_drills SET status = 'failed' WHERE drill_id = %s", (drill_id,))
            raise HTTPException(500, f"Analysis failed: {e}")

        # ─── Save results + mark token used ───
        with dict_cursor(conn) as cur:
            cur.execute("""
                UPDATE free_drills
                SET status = 'analyzed',
                    transcript = %s,
                    signals = %s,
                    metrics = %s,
                    diagnosis = %s,
                    gap = %s,
                    coaching = %s,
                    before_after = %s,
                    analyzed_at = NOW()
                WHERE drill_id = %s
            """, (
                analysis["transcribed_text"],
                json.dumps(analysis["signals"]),
                json.dumps(analysis["metrics"]),
                json.dumps(analysis["diagnosis"]),
                json.dumps(analysis["gap"]),
                json.dumps(analysis["coaching"]),
                json.dumps(analysis["before_after_rewrite"]),
                drill_id,
            ))

            cur.execute("UPDATE session_tokens SET used_at = NOW() WHERE jti = %s", (jti,))

        # Merge lead info into response
        analysis["drill_id"] = drill_id
        analysis["user_id"] = email
        analysis["name"] = drill.get("name") or "Guest"
        analysis["email"] = email
        analysis["stage"] = drill.get("stage") or "early"
        analysis["question"] = drill.get("question_prompt") or "Tell me about yourself."

        return analysis
    finally:
        conn.close()


# ============================================================
# ANALYSIS PIPELINE
# ============================================================
def run_analysis_pipeline(drill) -> dict:
    mode = drill["mode"]
    duration = drill.get("duration_seconds") or 30

    # 1. Get transcript
    if mode == "text":
        transcript = drill["raw_text"] or ""
    else:
        transcript = transcribe_from_r2(drill["audio_url"])

    # 2. Rule-based signals
    signals = compute_signals(transcript, duration, mode)

    # 3. LLM diagnosis
    llm = llm_diagnose(transcript, signals, drill.get("question_type", "intro"))

    return {
        "transcribed_text": transcript,
        "signals": signals,
        "metrics": llm["metrics"],
        "diagnosis": llm["diagnosis"],
        "gap": llm["gap"],
        "coaching": llm["coaching"],
        "before_after_rewrite": llm["before_after_rewrite"],
    }


def transcribe_from_r2(audio_url: str) -> str:
    """Download audio from R2, send to Whisper."""
    if not audio_url:
        return ""

    # Download
    key = audio_url.split("/")[-1]
    key_path = f"drills/{key}"
    audio_bytes = download_from_r2(key_path)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        path = f.name

    try:
        import openai
        with open(path, "rb") as f:
            result = openai.Audio.transcribe("whisper-1", f)
        return result.get("text", "")
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# ─── Signals ───
FILLERS = ["um", "uh", "like", "actually", "basically", "you know", "so", "well",
           "just", "really", "kind of", "sort of", "i mean", "right"]


def compute_signals(transcript: str, duration: int, mode: str) -> dict:
    import re
    words = [w for w in transcript.lower().split() if w]
    wc = len(words)
    duration = max(duration, 1)
    wpm = round((wc / duration) * 60)

    sentences = [s.strip() for s in re.split(r"[.!?]+", transcript) if s.strip()]
    lens = [len(s.split()) for s in sentences]
    avg_len = round(sum(lens) / len(lens)) if lens else 0
    longest = max(lens) if lens else 0

    breakdown = {}
    total_fillers = 0
    for f_word in FILLERS:
        pattern = r"\b" + re.escape(f_word).replace(r"\ ", r"\s+") + r"\b"
        matches = re.findall(pattern, transcript, flags=re.IGNORECASE)
        if matches:
            breakdown[f_word] = len(matches)
            total_fillers += len(matches)

    filler_pct = round((total_fillers / wc) * 100, 1) if wc else 0

    marker = re.search(r"\b(first|the point|what matters|the key|the main)\b", transcript, re.IGNORECASE)
    if marker:
        prefix_words = len(transcript[:marker.start()].split())
        ttp = max(3, round((prefix_words / max(wc, 1)) * duration))
    else:
        ttp = round(duration * 0.6)

    long_pauses = max(0, round((duration - wc / 3) / 4)) if mode == "voice" else 0

    return {
        "word_count": wc,
        "words_per_minute": wpm,
        "duration_seconds": duration,
        "filler_words": {
            "total": total_fillers,
            "percentage": filler_pct,
            "breakdown": breakdown,
        },
        "sentences": {
            "average_length": avg_len,
            "longest": longest,
            "total": len(sentences),
        },
        "long_pauses": list(range(long_pauses)),
        "main_point_delay_seconds": ttp,
    }


# ─── LLM Diagnosis ───
def llm_diagnose(transcript: str, signals: dict, question_type: str) -> dict:
    """Uses the existing Gemini service."""

    prompt = f"""You are an executive communication coach. Analyze the candidate's response.

QUESTION TYPE: {question_type}

TRANSCRIPT:
"{transcript}"

SIGNALS:
- Words per minute: {signals['words_per_minute']}
- Filler words: {signals['filler_words']['total']} ({signals['filler_words']['percentage']}%)
- Average sentence length: {signals['sentences']['average_length']} words
- Longest sentence: {signals['sentences']['longest']} words
- Time to main point: {signals['main_point_delay_seconds']}s

Return ONLY a JSON object with this exact structure:
{{
  "metrics": {{ "clarity": 0-100, "structure": 0-100, "impact": 0-100 }},
  "diagnosis": {{
    "pattern_name": "Short memorable name (e.g. The Amplifier, The Rambler)",
    "pattern_description": "1-2 sentences describing the pattern"
  }},
  "gap": {{
    "what_got_lost": "What specific thing got lost in their answer",
    "unspoken_gap": "The unspoken gap between intent and impact"
  }},
  "coaching": {{
    "one_thing_to_change": "One specific, actionable change"
  }},
  "before_after_rewrite": {{
    "executive_version": "A 2-3 sentence executive version of their answer"
  }}
}}

Be specific. Cite exact phrases from the transcript."""

    return gemini_generate_json(prompt)
