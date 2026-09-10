import os
import json
import re
import google.generativeai as genai

# Initialize Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
model = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3.6-flash')
        print("✅ Gemini API configured successfully")
    except Exception as e:
        print(f"⚠️ Gemini API configuration error: {e}")


def call_gemini_api(prompt: str, max_retries: int = 2):
    """
    Call Gemini API with simple retry logic.

    Note: Timeout is handled by the caller (analysis_service.py) via
    asyncio.wait_for + asyncio.to_thread. This function only handles:
      - Retry on transient errors
      - JSON parsing

    Args:
        prompt: The prompt to send to Gemini
        max_retries: Number of retry attempts on transient failure

    Returns:
        Parsed JSON response as dict, or None on failure
    """
    if not GEMINI_API_KEY or not model:
        print("⚠️ Gemini not available - API key or model missing")
        return None

    for attempt in range(max_retries + 1):
        try:
            print(f"🔄 Calling Gemini API (attempt {attempt + 1}/{max_retries + 1})...")

            response = model.generate_content(prompt)

            if not response or not response.text:
                print("⚠️ Empty response from Gemini")
                if attempt < max_retries:
                    continue
                return None

            print(f"✅ Gemini API response received: {len(response.text)} chars")
            print(f"📝 Raw response preview: {response.text[:200]}...")

            result = parse_gemini_response(response.text)
            if result:
                print("✅ Successfully parsed JSON from Gemini")
                return result

            print(f"⚠️ Failed to parse Gemini response (attempt {attempt + 1})")
            if attempt < max_retries:
                continue
            return None

        except Exception as e:
            print(f"❌ Gemini API Error (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                continue
            return None

    return None


def parse_gemini_response(response_text: str) -> dict:
    """
    Parse Gemini response text into a Python dictionary.
    Handles markdown code blocks and plain JSON.
    """
    if not response_text:
        return {}

    text = response_text.strip()

    # Try to extract JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_pattern, text)

    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass

    # Try to find JSON-like structure with braces
    brace_pattern = r'\{[\s\S]*\}'
    matches = re.findall(brace_pattern, text)

    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    print(f"⚠️ Could not parse Gemini response: {text[:100]}...")
    return {}


async def test_gemini_api():
    """Test if Gemini API is working."""
    config_status = {
        "gemini_key_set": bool(GEMINI_API_KEY),
        "model_initialized": bool(model),
        "api_key_length": len(GEMINI_API_KEY) if GEMINI_API_KEY else 0,
        "model_name": "gemini-3.6-flash" if model else "None"
    }

    if not GEMINI_API_KEY or not model:
        return {
            "success": False,
            "message": "Gemini not configured",
            "config": config_status
        }

    try:
        test_prompt = "Reply with exactly: 'Gemini is working correctly!'"
        response = model.generate_content(test_prompt)
        return {
            "success": True,
            "message": "Gemini API is working!",
            "response": response.text if response else "No response",
            "config": config_status
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Gemini API error: {str(e)}",
            "config": config_status
        }
