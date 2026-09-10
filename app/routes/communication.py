from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Response
from typing import List, Optional, Dict, Any
from app.models.schemas import (
    CommunicationRequest,
    PremiumCommunicationAnalysisRequest,
    AnalysisMode,
    QuestionType,
)
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.utils.scenarios import SCENARIOS
import logging
import io
import os
import openai
import json

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# EXISTING ENDPOINT - Deep Communication Analysis
# ============================================================

@router.post("/analyze")
async def analyze_communication(request: CommunicationRequest):
    """
    Deep Communication Analysis for Front Page Testing.
    Scenario-based, up to 3 attempts.
    """
    try:
        print("=" * 60)
        print("🧠 THE UNSPOKEN AI ANALYST")
        print(f"Scenario: {request.scenario_id}")

        # Extract attempts
        attempts_data = []

        if request.attempts:
            attempts_data = [{
                'attempt': a.attempt,
                'response': a.response,
                'mode': a.mode
            } for a in request.attempts]
        elif request.response:
            attempts_data = [{
                'attempt': request.attempt or 1,
                'response': request.response,
                'mode': request.mode or 'text'
            }]
            if request.previous_attempts:
                for prev in request.previous_attempts:
                    attempts_data.insert(0, {
                        'attempt': prev.get('attempt', 1),
                        'response': prev.get('response', ''),
                        'mode': prev.get('mode', 'text')
                    })
        else:
            return {"success": False, "message": "No attempt data provided"}

        if len(attempts_data) > 3:
            return {"success": False, "message": "Maximum 3 attempts allowed per scenario."}

        service = AnalysisService()
        result = await service.analyze_communication_deep(
            scenario_id=request.scenario_id,
            attempts_data=attempts_data
        )
        return result

    except Exception as e:
        print(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


@router.get("/scenarios")
async def get_scenarios():
    """Get all practice scenarios."""
    return {"success": True, "scenarios": SCENARIOS}


# ============================================================
# TEXT ANALYSIS - Deterministic-first
# ============================================================

@router.post("/analyze/premium")
async def analyze_premium_communication(
    request: PremiumCommunicationAnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service),
):
    """
    Text-based communication analysis.

    Deterministic signals computed locally.
    Single LLM call for qualitative parts (pattern, gap, coaching, rewrite).
    """
    try:
        logger.info(f"Premium analysis - Mode: {request.mode}, Question: {request.question_type}")

        if not request.text or len(request.text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Text must be at least 10 characters long",
            )

        # Estimate duration from word count (~150 wpm typed)
        words = len(request.text.split())
        estimated_duration = max(10, int(words / 2.5))

        result = await service.analyze_deterministic(
            transcript=request.text,
            duration_seconds=estimated_duration,
            segments=None,
            question_type=request.question_type.value if hasattr(request.question_type, "value") else str(request.question_type),
        )

        result["transcribed_text"] = request.text
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Premium analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ============================================================
# SUPPORTING ENDPOINTS
# ============================================================

@router.get("/analysis/modes")
async def get_analysis_modes():
    return {
        "success": True,
        "modes": [
            {"value": "voice", "label": "Voice (30s)"},
            {"value": "text", "label": "Type (60s)"},
        ],
    }


@router.get("/analysis/question-types")
async def get_question_types():
    return {
        "success": True,
        "question_types": [
            {
                "value": "intro",
                "label": "Introduce Yourself",
                "prompt": "Tell me about yourself - your background, what you do, and what drives you professionally.",
            },
            {
                "value": "project",
                "label": "Current Project",
                "prompt": "Tell me about a current project or initiative you're leading or involved in.",
            },
        ],
    }


@router.get("/analysis/health")
async def analysis_health_check():
    return {
        "status": "healthy",
        "service": "communication-analysis",
        "endpoints": [
            "/api/communication/analyze",
            "/api/communication/analyze/premium",
            "/api/communication/analyze/voice",
            "/api/communication/scenarios",
            "/api/communication/analysis/modes",
            "/api/communication/analysis/question-types",
        ],
    }


# ============================================================
# GROQ SETUP
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = None

if GROQ_API_KEY:
    try:
        groq_client = openai.OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        print("✅ Groq client configured successfully")
    except Exception as e:
        print(f"⚠️ Groq client error: {e}")
else:
    print("⚠️ GROQ_API_KEY not set - voice transcription will fail")


# ============================================================
# HELPER - Groq transcription with segment timestamps
# ============================================================

def transcribe_with_segments(audio_file, client):
    """
    Transcribe audio with Groq Whisper, requesting segment timestamps.

    Returns:
        (text: str, segments: list[dict], detected_duration: float)
    """
    response = client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=audio_file,
        response_format="verbose_json",
        timestamp_granularities=["segment"],
        language="en",
    )

    # verbose_json returns an object (or dict) with .text and .segments
    text = getattr(response, "text", None)
    segments_raw = getattr(response, "segments", None)

    # Some SDK versions return dicts
    if text is None and isinstance(response, dict):
        text = response.get("text", "")
    if segments_raw is None and isinstance(response, dict):
        segments_raw = response.get("segments", [])

    text = text or ""
    segments_raw = segments_raw or []

    segments = []
    for s in segments_raw:
        if isinstance(s, dict):
            segments.append({
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "text": s.get("text", ""),
            })
        else:
            segments.append({
                "start": float(getattr(s, "start", 0.0)),
                "end": float(getattr(s, "end", 0.0)),
                "text": getattr(s, "text", ""),
            })

    detected_duration = segments[-1]["end"] if segments else 0.0
    return text, segments, detected_duration


# ============================================================
# VOICE ANALYSIS - Deterministic-first
# ============================================================

@router.options("/analyze/voice")
async def options_voice():
    """Handle CORS preflight for voice endpoint."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "https://theunspoken.co.in",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        },
    )


@router.post("/analyze/voice")
async def analyze_voice(
    audio: UploadFile = File(...),
    question_type: str = Form("intro"),
    mode: str = Form("voice"),
    duration: int = Form(0),
    service: AnalysisService = Depends(get_analysis_service),
):
    """
    Voice analysis: Groq Whisper → deterministic signals → 1 LLM call.

    Response shape (kept compatible with previous frontend):
      { success, transcribed_text, signals, metrics, diagnosis, gap, coaching, before_after_rewrite }
    """
    try:
        logger.info(f"🎤 Voice analysis - question={question_type}, duration={duration}s")

        # ─── Read & validate audio ───
        audio_bytes = await audio.read()
        audio_size = len(audio_bytes)
        logger.info(f"📊 Audio size: {audio_size} bytes")

        if audio_size == 0:
            return {"success": False, "error": "No audio data received."}

        if audio_size > 25 * 1024 * 1024:
            return {"success": False, "error": "Audio too large (max 25MB)."}

        if not GROQ_API_KEY or not groq_client:
            return {
                "success": False,
                "error": "Voice transcription not configured. Please type your response.",
                "fallback_to_text": True,
            }

        # ─── Transcribe with segments ───
        logger.info("🔄 Sending to Groq Whisper...")

        file_extension = ".webm"
        if audio.content_type:
            ct = audio.content_type.lower()
            if "wav" in ct: file_extension = ".wav"
            elif "mp3" in ct or "mpeg" in ct: file_extension = ".mp3"
            elif "ogg" in ct: file_extension = ".ogg"
            elif "flac" in ct: file_extension = ".flac"
            elif "m4a" in ct or "mp4" in ct: file_extension = ".m4a"

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"recording{file_extension}"

        try:
            transcribed_text, segments, detected_duration = transcribe_with_segments(
                audio_file, groq_client
            )
        except Exception as e:
            err = str(e)
            logger.error(f"❌ Groq error: {err}")
            if "invalid_media_file" in err:
                return {"success": False, "error": "Audio format not recognized."}
            if "file is too large" in err:
                return {"success": False, "error": "Audio too large."}
            return {"success": False, "error": f"Transcription failed: {err}"}

        if not transcribed_text or len(transcribed_text.strip()) < 3:
            return {
                "success": False,
                "error": "No clear speech detected.",
                "transcribed_text": transcribed_text,
            }

        logger.info(f"✅ Transcript: {len(transcribed_text)} chars")
        logger.info(f"📝 Preview: {transcribed_text[:100]}...")

        # ─── Determine duration ───
        duration_used = duration or detected_duration or 30

        # ─── Run deterministic analysis ───
        logger.info("🔍 Running deterministic analysis...")
        result = await service.analyze_deterministic(
            transcript=transcribed_text,
            duration_seconds=duration_used,
            segments=segments,
            question_type=question_type,
        )

        result["transcribed_text"] = transcribed_text
        logger.info("✅ Voice analysis complete")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Voice analysis error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Analysis failed: {str(e)}"}


# ============================================================
# TEST GROQ API ENDPOINT
# ============================================================

@router.get("/test-groq")
async def test_groq_api():
    """Test if Groq API is configured and working."""
    config_status = {
        "groq_key_set": bool(GROQ_API_KEY),
        "groq_client_initialized": bool(groq_client),
        "api_key_length": len(GROQ_API_KEY) if GROQ_API_KEY else 0,
    }

    if not GROQ_API_KEY or not groq_client:
        return {
            "success": False,
            "message": "Groq API not configured",
            "config": config_status,
        }

    try:
        import wave

        # Build a 1-second silent WAV to test the API
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 16000)

        test_file = io.BytesIO(wav_io.getvalue())
        test_file.name = "test.wav"

        test_response = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=test_file,
            response_format="text",
        )

        return {
            "success": True,
            "message": "Groq API is working!",
            "response": test_response if isinstance(test_response, str) else test_response.text,
            "config": config_status,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Groq API error: {str(e)}",
            "config": config_status,
        }
