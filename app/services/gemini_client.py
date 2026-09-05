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
        model = genai.GenerativeModel('gemini-2.5-flash')
        print("✅ Gemini API configured successfully")
    except Exception as e:
        print(f"⚠️ Gemini API configuration error: {e}")

def call_gemini_api(prompt: str):
    """Call Gemini API with the prompt."""
    try:
        if not GEMINI_API_KEY or not model:
            print("⚠️ Gemini not available - API key or model missing")
            return None
        
        print("🔄 Calling Gemini API...")
        response = model.generate_content(prompt)
        print(f"✅ Gemini API response received: {len(response.text)} chars")
        
        text = response.text
        print(f"📝 Raw response preview: {text[:200]}...")
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print("✅ Successfully parsed JSON from Gemini")
            return result
        else:
            if '```json' in text:
                json_text = text.split('```json')[1].split('```')[0].strip()
                try:
                    result = json.loads(json_text)
                    print("✅ Extracted JSON from markdown")
                    return result
                except:
                    pass
            return None
            
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_gemini_api():
    """Test if Gemini API is working."""
    config_status = {
        "gemini_key_set": bool(GEMINI_API_KEY),
        "model_initialized": bool(model),
        "api_key_length": len(GEMINI_API_KEY) if GEMINI_API_KEY else 0
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
            "response": response.text,
            "config": config_status
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Gemini API error: {str(e)}",
            "config": config_status
        }
