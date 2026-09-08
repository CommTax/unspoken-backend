from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Response
from typing import List, Optional
from app.models.schemas import (
    CommunicationRequest,
    PremiumCommunicationAnalysisRequest,
    PremiumCommunicationAnalysisResponse,
    AnalysisMode,
    QuestionType
)
from app.services.analysis_service import AnalysisService, get_analysis_service
from app.utils.scenarios import SCENARIOS
import logging
import io
import os
import openai
from tempfile import NamedTemporaryFile
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================
# EXISTING ENDPOINT - Deep Communication Analysis
# ============================================================

@router.post("/analyze")
async def analyze_communication(request: CommunicationRequest):
    """
    Communication Analysis for Front Page Testing.
    This handles the voice/text practice and provides feedback.
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
        
        # Create service instance
        service = AnalysisService()
        
        # Call the analysis service
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
# UPDATED ENDPOINT - Minimal Premium Communication Analysis
# ============================================================

@router.post("/analyze/premium")
async def analyze_premium_communication(
    request: PremiumCommunicationAnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service)
):
    """
    Premium Communication Analysis - Minimal Version
    
    Returns ONLY the essential fields needed for conversion:
    - Impact Score (from metrics)
    - Pattern Name & Description (from diagnosis)
    - What Got Lost & Unspoken Gap (from gap analysis)
    - Executive Version (1 line only, from before_after_rewrite)
    
    All other fields are now static/blurred in the frontend.
    This reduces AI processing cost by ~65% and response time by ~60%.
    """
    try:
        logger.info(f"Premium analysis request (minimal) - Mode: {request.mode}, Question: {request.question_type}")
        
        # Validate text length
        if not request.text or len(request.text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Text must be at least 10 characters long"
            )
        
        # Get minimal analysis from service
        response = await service.analyze_premium_communication_minimal(request)
        
        logger.info("Minimal premium analysis completed successfully")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Premium analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


# ============================================================
# SUPPORTING ENDPOINTS
# ============================================================

@router.get("/analysis/modes")
async def get_analysis_modes():
    """Get available analysis modes."""
    return {
        "success": True,
        "modes": [
            {"value": "voice", "label": "Voice (45s)"},
            {"value": "text", "label": "Type (60s)"}
        ]
    }


@router.get("/analysis/question-types")
async def get_question_types():
    """Get available question types."""
    return {
        "success": True,
        "question_types": [
            {"value": "intro", "label": "Introduce Yourself", "prompt": "Tell me about yourself - your background, what you do, and what drives you professionally."},
            {"value": "project", "label": "Current Project", "prompt": "Tell me about a current project or initiative you're leading or involved in."}
        ]
    }


@router.get("/analysis/health")
async def analysis_health_check():
    """Health check for analysis service."""
    return {
        "status": "healthy",
        "service": "communication-analysis",
        "endpoints": [
            "/api/communication/analyze",
            "/api/communication/analyze/premium",
            "/api/communication/scenarios",
            "/api/communication/analysis/modes",
            "/api/communication/analysis/question-types"
        ]
    }


# ============================================================
# BATCH ANALYSIS ENDPOINT (Optional - keep for reference)
# ============================================================

@router.post("/analyze/batch")
async def analyze_batch_communication(
    requests: List[PremiumCommunicationAnalysisRequest],
    service: AnalysisService = Depends(get_analysis_service)
):
    """
    Analyze multiple communications in batch.
    """
    try:
        results = []
        for request in requests:
            try:
                result = await service.analyze_premium_communication_minimal(request)
                results.append({
                    "success": True,
                    "request": {
                        "mode": request.mode,
                        "question_type": request.question_type,
                        "text_preview": request.text[:50] + "..."
                    },
                    "response": result
                })
            except Exception as e:
                results.append({
                    "success": False,
                    "request": {
                        "mode": request.mode,
                        "question_type": request.question_type,
                        "text_preview": request.text[:50] + "..."
                    },
                    "error": str(e)
                })
        
        return {
            "success": True,
            "results": results,
            "total": len(results),
            "successful": sum(1 for r in results if r["success"])
        }
        
    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch analysis failed: {str(e)}"
        )


# ============================================================
# VOICE ANALYSIS ENDPOINT - Using Groq Whisper (FREE)
# ============================================================

# Initialize Groq client with your API key
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = None

if GROQ_API_KEY:
    try:
        import openai
        groq_client = openai.OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )
        print("✅ Groq client configured successfully")
    except Exception as e:
        print(f"⚠️ Groq client error: {e}")
else:
    print("⚠️ GROQ_API_KEY not set - voice transcription will use fallback")


@router.options("/analyze/voice")
async def options_voice():
    """Handle CORS preflight for voice endpoint"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "https://theunspoken.co.in",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "3600",
        }
    )


@router.post("/analyze/voice")
async def analyze_voice(
    audio: UploadFile = File(...),
    question_type: str = Form("intro"),
    mode: str = Form("voice"),
    duration: int = Form(0),
    service: AnalysisService = Depends(get_analysis_service)
):
    """
    Analyze voice recording using Groq's free Whisper API.
    
    This endpoint:
    1. Receives audio as multipart/form-data
    2. Transcribes audio using Groq Whisper (free, high accuracy)
    3. Analyzes the transcribed text using your AI
    4. Returns the combined results
    
    Works on all devices including mobile!
    """
    try:
        logger.info(f"🎤 Voice analysis request - Duration: {duration}s, Question: {question_type}")
        
        # Log audio file details
        logger.info(f"📁 Audio file: {audio.filename}, Content-Type: {audio.content_type}")
        
        # Read audio bytes
        audio_bytes = await audio.read()
        audio_size = len(audio_bytes)
        logger.info(f"📊 Audio size: {audio_size} bytes")
        
        # Validate audio
        if audio_size == 0:
            logger.error("❌ Empty audio file received")
            return {
                "success": False,
                "error": "No audio data received. Please try recording again."
            }
        
        if audio_size > 25 * 1024 * 1024:  # 25MB limit
            logger.error(f"❌ Audio too large: {audio_size} bytes")
            return {
                "success": False,
                "error": "Audio file too large. Please record a shorter response (max 25MB)."
            }
        
        # Check if Groq is configured
        if not GROQ_API_KEY or not groq_client:
            logger.warning("⚠️ Groq API not configured")
            return {
                "success": False,
                "error": "Voice transcription service not configured. Please try typing your response.",
                "fallback_to_text": True
            }
        
        # Transcribe using Groq Whisper
        logger.info("🔄 Sending to Groq Whisper for transcription...")
        
        try:
            # Create a file-like object with proper filename
            audio_file = io.BytesIO(audio_bytes)
            
            # Determine file extension from content type
            file_extension = ".webm"  # default
            if audio.content_type:
                if "webm" in audio.content_type:
                    file_extension = ".webm"
                elif "wav" in audio.content_type:
                    file_extension = ".wav"
                elif "mp3" in audio.content_type or "mpeg" in audio.content_type:
                    file_extension = ".mp3"
                elif "ogg" in audio.content_type:
                    file_extension = ".ogg"
                elif "flac" in audio.content_type:
                    file_extension = ".flac"
                elif "m4a" in audio.content_type or "mp4" in audio.content_type:
                    file_extension = ".m4a"
            
            # Set filename for Groq
            audio_file.name = f"recording{file_extension}"
            logger.info(f"📝 Sending file as: {audio_file.name}")
            
            # Transcribe
            transcript_response = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text",
                language="en"
            )
            
            # Extract transcribed text
            transcribed_text = transcript_response if isinstance(transcript_response, str) else transcript_response.text
            
            if not transcribed_text or len(transcribed_text.strip()) < 3:
                logger.warning("⚠️ No clear speech detected in transcription")
                return {
                    "success": False,
                    "error": "No clear speech detected. Please try speaking more clearly or type your response.",
                    "transcribed_text": transcribed_text
                }
            
            logger.info(f"✅ Transcription complete: {len(transcribed_text)} chars")
            logger.info(f"📝 Preview: {transcribed_text[:100]}...")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Groq transcription error: {error_msg}")
            
            # Provide more specific error messages
            if "invalid_media_file" in error_msg:
                return {
                    "success": False,
                    "error": "The audio format was not recognized. Please try recording again with a different format or use text input.",
                    "details": "Audio format not supported"
                }
            elif "file is too large" in error_msg:
                return {
                    "success": False,
                    "error": "Audio file is too large. Please record a shorter response (max 25MB)."
                }
            else:
                return {
                    "success": False,
                    "error": f"Transcription failed: {error_msg}",
                    "transcribed_text": None
                }
        
        # Now analyze the transcribed text using your existing analysis
        logger.info("🔍 Analyzing transcribed text with AI...")
        
        # Create a PremiumCommunicationAnalysisRequest from the transcribed text
        from app.models.schemas import PremiumCommunicationAnalysisRequest, QuestionType, AnalysisMode
        
        # Convert string to enum
        mode_enum = AnalysisMode.VOICE if mode == "voice" else AnalysisMode.TEXT
        question_type_enum = QuestionType.INTRO if question_type == "intro" else QuestionType.PROJECT
        
        analysis_request = PremiumCommunicationAnalysisRequest(
            text=transcribed_text,
            mode=mode_enum,
            question_type=question_type_enum
        )
        
        # Get the analysis
        analysis_result = await service.analyze_premium_communication_minimal(analysis_request)
        
        logger.info("✅ Voice analysis complete")
        
        # Return combined result with transcribed text (NO audio bytes in response)
        return {
            "success": True,
            "transcribed_text": transcribed_text,
            **analysis_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Voice analysis error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Analysis failed: {str(e)}"
        }


# ============================================================
# TEST GROQ API ENDPOINT
# ============================================================

@router.get("/test-groq")
async def test_groq_api():
    """Test if Groq API is configured and working."""
    config_status = {
        "groq_key_set": bool(GROQ_API_KEY),
        "groq_client_initialized": bool(groq_client),
        "api_key_length": len(GROQ_API_KEY) if GROQ_API_KEY else 0
    }
    
    if not GROQ_API_KEY or not groq_client:
        return {
            "success": False,
            "message": "Groq API not configured",
            "config": config_status
        }
    
    try:
        # Create a simple test - use a small audio file instead of text
        # Generate a simple WAV file (1 second of silence)
        import wave
        import io
        
        # Create a minimal WAV file
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b'\x00\x00' * 16000)  # 1 second of silence
        
        wav_data = wav_io.getvalue()
        
        # Test transcription with the WAV file
        test_file = io.BytesIO(wav_data)
        test_file.name = "test.wav"
        
        test_response = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=test_file,
            response_format="text"
        )
        
        return {
            "success": True,
            "message": "Groq API is working!",
            "response": test_response if isinstance(test_response, str) else test_response.text,
            "config": config_status
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Groq API error: {str(e)}",
            "config": config_status
        }


# ============================================================
# EXPORT ROUTER
# ============================================================

# Note: The router is imported and used in main.py
# All endpoints are accessible at /api/communication/*
