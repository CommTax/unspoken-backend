import os
import json
import google.generativeai as genai
from typing import Dict, Any
from app.models.schemas import CommunicationAnalysis

class GeminiService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "max_output_tokens": 2048,
            }
        )
        
        self.ANALYSIS_PROMPT = """
You are a world-class executive communication coach with 20 years of experience.
Analyze the following transcript and provide your assessment in VALID JSON format:

{
    "communication_tax_score": integer 0-100,
    "clarity_rating": "Excellent" or "Good" or "Needs Improvement" or "Poor",
    "structure_rating": "Excellent" or "Good" or "Needs Improvement" or "Poor",
    "confidence_rating": "Excellent" or "Good" or "Needs Improvement" or "Poor",
    "key_insights": ["insight1", "insight2", "insight3", "insight4", "insight5"],
    "actionable_recommendations": ["rec1", "rec2", "rec3", "rec4", "rec5"],
    "follow_up_questions": ["q1", "q2"],
    "estimated_value_leakage": "₹X-Y Lakhs per year"
}

Transcript: {transcript}
"""

def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
    try:
        prompt = self.ANALYSIS_PROMPT.format(transcript=transcript)
        response = self.model.generate_content(prompt)
        
        # Log the raw response for debugging
        print(f"Raw response: {response.text}")
        
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        result = json.loads(text.strip())
        validated = CommunicationAnalysis(**result)
        
        return {"success": True, "analysis": validated.model_dump()}
    except Exception as e:
        print(f"Error: {e}")
        return {"success": False, "error": str(e)}
