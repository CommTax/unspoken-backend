import os
import json
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
        
        self.ANALYSIS_PROMPT = """
You are an executive communication coach with 20 years of experience. Analyze this transcript and return ONLY valid JSON.

Transcript: {transcript}

Evaluate the speaker on these 4 dimensions:
1. Thinking - Quality of ideas, reasoning depth, mental clarity, and strategic perspective
2. Structure - Organization, logical flow, and how ideas are sequenced
3. Clarity - How clearly the message is communicated, precision of language, freedom from ambiguity
4. Influence - Ability to persuade, create conviction, drive action, and inspire confidence

Output must be exactly this format:
{
    "overall_comment": "A 2-3 sentence summary of where this person stands as a communicator overall.",
    "thinking": {
        "rating": "Strong" or "Good" or "Needs Work" or "Critical Gap",
        "feedback": "Specific, actionable feedback about their thinking quality."
    },
    "structure": {
        "rating": "Strong" or "Good" or "Needs Work" or "Critical Gap",
        "feedback": "Specific, actionable feedback about their structure."
    },
    "clarity": {
        "rating": "Strong" or "Good" or "Needs Work" or "Critical Gap",
        "feedback": "Specific, actionable feedback about their clarity."
    },
    "influence": {
        "rating": "Strong" or "Good" or "Needs Work" or "Critical Gap",
        "feedback": "Specific, actionable feedback about their influence."
    },
    "good_points": ["What they're doing well - point 1", "point 2", "point 3"],
    "areas_to_cover": ["What they need to work on - point 1", "point 2", "point 3"],
    "follow_up_questions": ["Question 1 to understand their communication context better", "Question 2"]
}

Be brutally honest but constructive. Give specific examples from the transcript where possible.
Return ONLY the JSON. No other text.
"""

    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        try:
            prompt = self.ANALYSIS_PROMPT.replace("{transcript}", transcript)
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
    
    def get_follow_up(self, transcript: str, context: str) -> str:
        """Generate a natural language follow-up response"""
        try:
            prompt = f"""
Based on this communication transcript: "{transcript}"

Context: {context}

Generate a natural, conversational follow-up response that asks 1-2 relevant follow-up questions 
to better understand the user's communication style or situation.

Be empathetic, professional, and genuinely curious. Keep it under 3 sentences total.
"""
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"I'd like to understand more about your communication context. Could you share a specific example?"
