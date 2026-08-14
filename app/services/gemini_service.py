import os
import json
import re
import google.generativeai as genai
from typing import Dict, Any
from app.models.schemas import CommunicationAnalysis, DimensionFeedback

class GeminiService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "max_output_tokens": 2048,
            }
        )
        
        self.ANALYSIS_PROMPT = """Analyze this transcript. Return ONLY valid JSON. No markdown, no explanations, no extra text.

Transcript: {transcript}

Return JSON exactly like this. Use these exact keys. For ratings, use only: "Strong", "Good", "Needs Work", or "Critical Gap".

{
    "overall_comment": "2-3 sentence summary",
    "thinking": {
        "rating": "Strong",
        "feedback": "feedback text"
    },
    "structure": {
        "rating": "Strong",
        "feedback": "feedback text"
    },
    "clarity": {
        "rating": "Strong",
        "feedback": "feedback text"
    },
    "influence": {
        "rating": "Strong",
        "feedback": "feedback text"
    },
    "good_points": ["point1", "point2", "point3"],
    "areas_to_cover": ["area1", "area2", "area3"],
    "follow_up_questions": ["q1", "q2"]
}"""

    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        try:
            # Use .replace() instead of .format() to avoid conflicts with JSON braces
            prompt = self.ANALYSIS_PROMPT.replace("{transcript}", transcript)
            response = self.model.generate_content(prompt)
            
            raw_text = response.text
            print(f"=== RAW RESPONSE ===")
            print(repr(raw_text))
            print("=== END RAW ===")
            
            text = raw_text.strip()
            
            # Remove markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            # Find JSON using regex
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            
            text = text.strip()
            print(f"=== CLEANED TEXT ===")
            print(repr(text))
            print("=== END CLEANED ===")
            
            result = json.loads(text)
            validated = CommunicationAnalysis(**result)
            
            return {"success": True, "analysis": validated.model_dump()}
        except Exception as e:
            print(f"=== ERROR ===")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def get_follow_up(self, transcript: str, context: str) -> str:
        try:
            prompt = f"Based on this transcript: '{transcript}' Context: {context}. Generate a natural follow-up response with 1-2 questions. Keep it under 3 sentences. Return only the text."
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"I'd like to understand more about your communication context. Could you share a specific example?"
