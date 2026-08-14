import os
import json
import re
import google.generativeai as genai
from typing import Dict, Any, List
from app.models.schemas import CommunicationAnalysis, DimensionFeedback, SpeechAnalytics
import time

class GeminiService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(
            model_name="models/gemini-flash-lite-latest",  # Faster model
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "max_output_tokens": 2048,  # Reduced for speed
            }
        )
        
        self.ANALYSIS_PROMPT = """Analyze this transcript. Address the person as "You". Return ONLY JSON.

Transcript: {transcript}

{
    "overall_comment": "2-3 sentence summary using 'you'",
    "thinking": {"rating": "Strong/Good/Needs Work/Critical Gap", "feedback": "feedback using 'you'"},
    "structure": {"rating": "Strong/Good/Needs Work/Critical Gap", "feedback": "feedback using 'you'"},
    "clarity": {"rating": "Strong/Good/Needs Work/Critical Gap", "feedback": "feedback using 'you'"},
    "influence": {"rating": "Strong/Good/Needs Work/Critical Gap", "feedback": "feedback using 'you'"},
    "good_points": ["point1", "point2", "point3"],
    "areas_to_cover": ["area1", "area2", "area3"],
    "follow_up_questions": ["q1", "q2"]
}"""

    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        try:
            # Calculate speech analytics first
            speech_analytics = self._calculate_speech_analytics(transcript)
            
            # Prepare prompt
            prompt = self.ANALYSIS_PROMPT.replace("{transcript}", transcript[:500])  # Limit transcript length
            
            # Call Gemini with timeout
            response = self.model.generate_content(prompt)
            
            raw_text = response.text
            print(f"Raw response: {raw_text[:200]}...")  # Log first 200 chars
            
            # Extract JSON
            text = raw_text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            
            result = json.loads(text.strip())
            result["speech_analytics"] = speech_analytics.model_dump()
            
            validated = CommunicationAnalysis(**result)
            return {"success": True, "analysis": validated.model_dump()}
            
        except Exception as e:
            print(f"Error: {e}")
            return {"success": False, "error": str(e)}
    
    def _calculate_speech_analytics(self, transcript: str) -> SpeechAnalytics:
        """Calculate words per minute and filler word count"""
        filler_words = ['um', 'uh', 'ah', 'er', 'like', 'you know', 'i mean', 'actually', 'basically', 'literally', 'sort of', 'kind of']
        
        words = re.findall(r'\b\w+\b', transcript.lower())
        total_words = len(words)
        
        total_fillers = 0
        filler_list = []
        for filler in filler_words:
            if ' ' in filler:
                count = len(re.findall(r'\b' + re.escape(filler) + r'\b', transcript.lower()))
                if count > 0:
                    total_fillers += count
                    filler_list.append(filler)
            else:
                count = words.count(filler)
                if count > 0:
                    total_fillers += count
                    filler_list.append(filler)
        
        estimated_minutes = max(1, total_words / 150)
        words_per_minute = int(total_words / estimated_minutes)
        filler_words_per_minute = int(total_fillers / estimated_minutes)
        
        return SpeechAnalytics(
            words_per_minute=words_per_minute,
            filler_words_per_minute=filler_words_per_minute,
            total_words=total_words,
            total_fillers=total_fillers,
            filler_word_list=filler_list
        )
    
    def get_follow_up(self, transcript: str, context: str) -> str:
        try:
            prompt = f"Based on this transcript: '{transcript}' Context: {context}. Generate a natural follow-up response with 1-2 questions. Keep it under 3 sentences. Return only the text."
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"I'd like to understand more about your communication context. Could you share a specific example?"
