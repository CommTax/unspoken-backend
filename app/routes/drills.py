# app/routes/drills.py
"""
Drill upload, capture, and analyze endpoints.

Flow (trial):
  1. POST /api/drills/upload          -> { drill_id }
  2. POST /api/drills/capture         -> { user_id, session_token, drill_id }
  3. POST /api/drills/analyze         -> full analysis payload
     (Authorization: Bearer <session_token>)

Flow (paid):
  1. POST /api/drills/upload          -> { drill_id }
  2. POST /api/drills/analyze         -> full analysis payload
     (Authorization: Bearer <otp_session_token>)

Rule-based metrics. One Gemini call per drill for qualitative only.
Executive rewrite is only generated for paid users.
"""

import os
import re
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
from app.services.gemini_client import call_gemini_api


router = APIRouter()

# ─── CONFIG ───
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-env")
JWT_ALGO = "HS256"
SESSION_EXPIRES_HOURS = int(os.getenv("SESSION_EXPIRES_HOURS", "24"))
TRIAL_CAP_PER_QUESTION = 2


# ─── AUTH HELPERS ───
def issue_session_token(email: str, trial: bool) -> tuple[str, str]:
    """Returns (jti, signed_token)."""
    jti = str(uuid.uuid4())
    now = datetime.utcnow()
    payload = {
        "sub": email,
        "jti": jti,
        "trial": trial,
        "iat": now,
        "exp": now + timedelta(hours=SESSION_EXPIRES_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return jti, token


def verify_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid session: {e}")


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
    question_slot: Optional[str] = None  # 'q1' | 'q2'
    mode: Optional[str] = "voice"


class AnalyzePayload(BaseModel):
    drill_id: str


# ============================================================
# POST /api/drills/upload
# ============================================================
@router.post("/upload")
async def upload_drill(
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    question_type: str = Form("intro"),
    question_slot: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    trial: Optional[str] = Form("true"),
    mode: str = Form("voice"),
    duration_seconds: int = Form(30),
):
    if mode == "voice" and not audio:
        raise HTTPException(400, "audio file required for voice mode")
    if mode == "text" and not text:
        raise HTTPException(400, "text required for text mode")

    drill_id = str(uuid.uuid4())
    audio_url = None

    if mode == "voice" and audio:
        try:
            content = await audio.read()
            key = f"drills/{drill_id}.webm"
            audio_url = upload_to_r2(key, content, content_type="audio/webm")
        except Exception as e:
            raise HTTPException(500, f"R2 upload failed: {e}")

    is_trial = str(trial).lower() == "true"

    conn = get_conn()
    try:
        with dict_cursor(conn) as cur:
            cur.execute("""
                INSERT INTO free_drills
                  (drill_id, status, mode, question_type, question_slot,
                   user_id, trial, audio_url, duration_seconds, raw_text)
                VALUES (%s, 'uploaded', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (drill_id, mode, question_type, question_slot,
                  user_id, is_trial, audio_url, duration_seconds, text))
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
            cur.execute("SELECT drill_id FROM free_drills WHERE drill_id = %s", (payload.drill_id,))
            if not cur.fetchone():
                raise HTTPException(404, "drill_id not found")

            # Link drill to email + slot
            cur.execute("""
                UPDATE free_drills
                SET email = %s, user_id = %s, question_slot = COALESCE(%s, question_slot)
                WHERE drill_id = %s
            """, (payload.email, payload.email, payload.question_slot, payload.drill_id))

            # Upsert trial user session
            cur.execute("""
                INSERT INTO user_sessions (email, name, stage, plan, current_day, total_days,
                                           questions_per_day, trials_per_question)
                VALUES (%s, %s, %s, 'trial', 1, 28, 2, 2)
                ON CONFLICT (email) DO UPDATE SET
                  name = EXCLUDED.name,
                  stage = EXCLUDED.stage,
                  updated_at = NOW()
            """, (payload.email, payload.name, payload.stage))

            # Issue a long-lived session token (NOT one-time-use)
            jti, token = issue_session_token(payload.email, trial=True)
            expires_at = datetime.utcnow() + timedelta(hours=SESSION_EXPIRES_HOURS)
            cur.execute("""
                INSERT INTO session_tokens (jti, email, drill_id, expires_at, trial)
                VALUES (%s, %s, %s, %s, TRUE)
            """, (jti, payload.email, payload.drill_id, expires_at))
    finally:
        conn.close()

    return {
        "user_id": payload.email,
        "session_token": token,
        "expires_in": SESSION_EXPIRES_HOURS * 3600,
        "drill_id": payload.drill_id,
    }


# ============================================================
# POST /api/drills/analyze
# ============================================================
@router.post("/analyze")
def analyze_drill(payload: AnalyzePayload,
                  token: str = Depends(bearer_token)):
    claims = verify_session_token(token)
    email = claims["sub"]
    is_trial = bool(claims.get("trial", False))

    conn = get_conn()
    try:
        with dict_cursor(conn) as cur:
            # Load drill + user
            cur.execute("""
                SELECT d.*, s.name, s.stage
                FROM free_drills d
                LEFT JOIN user_sessions s ON s.email = d.email
                WHERE d.drill_id = %s
            """, (payload.drill_id,))
            drill = cur.fetchone()
            if not drill:
                raise HTTPException(404, "Drill not found")

            # Ownership check for paid users
            if not is_trial and drill.get("email") and drill["email"] != email:
                raise HTTPException(403, "Not your drill")

            # Trial cap check
            if is_trial and drill.get("question_slot"):
                cur.execute("""
                    SELECT COUNT(*) AS n FROM free_drills
                    WHERE user_id = %s
                      AND question_slot = %s
                      AND trial = TRUE
                      AND status = 'analyzed'
                      AND drill_id <> %s
                """, (email, drill["question_slot"], payload.drill_id))
                prior = cur.fetchone()["n"]
                if prior >= TRIAL_CAP_PER_QUESTION:
                    raise HTTPException(403, detail={
                        "error": "TRIAL_CAP_REACHED",
                        "question": drill["question_slot"],
                    })

        # ─── Run analysis ───
        try:
            analysis = run_analysis_pipeline(drill, is_trial=is_trial)
        except Exception as e:
            with dict_cursor(conn) as cur:
                cur.execute("UPDATE free_drills SET status = 'failed' WHERE drill_id = %s",
                            (payload.drill_id,))
            raise HTTPException(500, f"Analysis failed: {e}")

        # ─── Save results ───
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
                json.dumps(analysis.get("before_after_rewrite") or {}),
                payload.drill_id,
            ))

        # Augment response
        analysis["drill_id"] = payload.drill_id
        analysis["user_id"] = email
        analysis["name"] = drill.get("name") or "Guest"
        analysis["email"] = email
        analysis["stage"] = drill.get("stage") or "early"
        analysis["question_type"] = drill.get("question_type") or "intro"
        analysis["question_slot"] = drill.get("question_slot")
        analysis["question_text"] = drill.get("question_prompt") or "Tell me about yourself."
        analysis["is_trial"] = is_trial
        # Executive rewrite is withheld for trial users
        if is_trial:
            analysis["before_after_rewrite"] = None

        return analysis
    finally:
        conn.close()


# ============================================================
# ANALYSIS PIPELINE
# ============================================================
def run_analysis_pipeline(drill, is_trial: bool) -> dict:
    mode = drill["mode"]
    duration = drill.get("duration_seconds") or 30

    # 1. Transcript
    if mode == "text":
        transcript = drill["raw_text"] or ""
    else:
        transcript = transcribe_from_r2(drill["audio_url"])

    # 2. Rule-based signals (free)
    signals = compute_signals(transcript, duration, mode)

    # 3. Rule-based metrics (free)
    metrics = compute_metrics(signals)

    # 4. One LLM call — qualitative only
    llm = llm_diagnose(
        transcript=transcript,
        signals=signals,
        metrics=metrics,
        question_type=drill.get("question_type", "intro"),
        want_rewrite=not is_trial,   # only paid gets the executive rewrite
    )

    return {
        "transcribed_text": transcript,
        "signals": signals,
        "metrics": metrics,
        "diagnosis": llm["diagnosis"],
        "gap": llm["gap"],
        "coaching": llm["coaching"],
        "before_after_rewrite": llm.get("before_after_rewrite"),
    }


def transcribe_from_r2(audio_url: str) -> str:
    if not audio_url:
        return ""
    key = audio_url.split("/")[-1]
    key_path = f"drills/{key}"
    audio_bytes = download_from_r2(key_path)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        path = f.name

    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        with open(path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=("audio.webm", f.read()),
                model="whisper-large-v3",
            )
        return result.text or ""
    except Exception as e:
        print(f"⚠️ Groq transcription failed: {e}")
        return ""
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# ─── Signals (free) ───
FILLERS = ["um", "uh", "like", "actually", "basically", "you know", "so", "well",
           "just", "really", "kind of", "sort of", "i mean", "right"]


def compute_signals(transcript: str, duration: int, mode: str) -> dict:
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

    marker = re.search(r"\b(first|the point|what matters|the key|the main)\b",
                       transcript, re.IGNORECASE)
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


# ─── Metrics (free, rule-based) ───
def _clamp(v, lo=30, hi=98):
    return max(lo, min(hi, round(v)))


def compute_metrics(signals: dict) -> dict:
    filler_pct = signals["filler_words"]["percentage"]
    avg_sent = signals["sentences"]["average_length"]
    longest = signals["sentences"]["longest"]
    ttp = signals["main_point_delay_seconds"]
    wpm = signals["words_per_minute"]
    pauses = len(signals["long_pauses"])

    clarity = 100 - (filler_pct * 4) - max(0, avg_sent - 18) * 1.5 - pauses * 3
    structure = 100 - (ttp / 2) - max(0, longest - 30) * 1.2
    impact = 100 - abs(wpm - 140) * 0.3 - (filler_pct * 2) - (ttp / 1.5)

    clarity = _clamp(clarity)
    structure = _clamp(structure)
    impact = _clamp(impact)

    overall = round(((clarity + structure + impact) / 3) / 10, 1)

    return {
        "clarity": clarity,
        "structure": structure,
        "impact": impact,
        "overall_score": overall,
    }


# ─── LLM diagnosis (qualitative only) ───
def llm_diagnose(transcript: str, signals: dict, metrics: dict,
                 question_type: str, want_rewrite: bool) -> dict:
    rewrite_field = ''
    rewrite_example = ''
    if want_rewrite:
        rewrite_field = ',\n  "before_after_rewrite": { "executive_version": "A 2-3 sentence executive version of their answer" }'
        rewrite_example = ',\n    "before_after_rewrite": {"executive_version": "Your executive version here."}'

    prompt = f"""You are an executive communication coach. Analyze the candidate's response.

QUESTION TYPE: {question_type}

TRANSCRIPT:
"{transcript}"

COMPUTED METRICS (do not recompute these — just use them for context):
- Clarity: {metrics['clarity']}/100
- Structure: {metrics['structure']}/100
- Impact: {metrics['impact']}/100
- Fillers: {signals['filler_words']['total']} ({signals['filler_words']['percentage']}%)
- Time to main point: {signals['main_point_delay_seconds']}s
- Words per minute: {signals['words_per_minute']}

Return ONLY a JSON object with this exact structure:
{{
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
  }}{rewrite_field}
}}

Be specific. Cite exact phrases from the transcript. No markdown. JSON only."""

    result = call_gemini_api(prompt)

    if not result:
        fallback = {
            "diagnosis": {
                "pattern_name": "The Communicator",
                "pattern_description": "You get your point across but could tighten the delivery."
            },
            "gap": {
                "what_got_lost": "Your credibility and authority in the first 10 seconds",
                "unspoken_gap": "Between your intent to sound confident and how you actually land"
            },
            "coaching": {
                "one_thing_to_change": "Lead with the point"
            },
        }
        if want_rewrite:
            fallback["before_after_rewrite"] = {"executive_version": "Your executive version here."}
        return fallback

    return result
