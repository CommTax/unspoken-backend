import os
import json
import re
import google.generativeai as genai
from typing import Dict, Any, List
from app.models.schemas import CommunicationAnalysis, DimensionFeedback, SpeechAnalytics

class GeminiService:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(
            model_name="models/gemini-flash-latest",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "max_output_tokens": 65536,
            }
        )
        
        self.ANALYSIS_PROMPT = """Analyze this transcript. Return ONLY valid JSON. No markdown, no explanations, no extra text.

IMPORTANT: Address the person directly using "You" and "your". Do not say "the speaker" or "they". Speak directly to them.

Transcript: {transcript}

Return JSON exactly like this. Use these exact keys. For ratings, use only: "Strong", "Good", "Needs Work", or "Critical Gap".

{
    "overall_comment": "2-3 sentence summary speaking directly to the person",
    "thinking": {
        "rating": "Strong",
        "feedback": "feedback text addressing 'you'"
    },
    "structure": {
        "rating": "Strong",
        "feedback": "feedback text addressing 'you'"
    },
    "clarity": {
        "rating": "Strong",
        "feedback": "feedback text addressing 'you'"
    },
    "influence": {
        "rating": "Strong",
        "feedback": "feedback text addressing 'you'"
    },
    "good_points": ["point1", "point2", "point3"],
    "areas_to_cover": ["area1", "area2", "area3"],
    "follow_up_questions": ["q1", "q2"]
}"""

    def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        try:
            # Calculate speech analytics
            speech_analytics = self._calculate_speech_analytics(transcript)
            
            prompt = self.ANALYSIS_PROMPT.replace("{transcript}", transcript)
            response = self.model.generate_content(prompt)
            
            raw_text = response.text
            print(f"=== RAW RESPONSE ===")
            print(repr(raw_text))
            print("=== END RAW ===")
            
            text = raw_text.strip()
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            
            text = text.strip()
            print(f"=== CLEANED TEXT ===")
            print(repr(text))
            print("=== END CLEANED ===")
            
            result = json.loads(text)
            
            # Add speech analytics to the result
            result["speech_analytics"] = speech_analytics.model_dump()
            
            validated = CommunicationAnalysis(**result)
            
            return {"success": True, "analysis": validated.model_dump()}
        except Exception as e:
            print(f"=== ERROR ===")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _calculate_speech_analytics(self, transcript: str) -> SpeechAnalytics:
        """Calculate words per minute and filler word count"""
        # Common filler words
        filler_words = [
            'um', 'uh', 'ah', 'er', 'like', 'you know', 'i mean', 
            'actually', 'basically', 'literally', 'sort of', 'kind of',
            'well', 'so', 'just', 'really', 'very'
        ]
        
        # Clean and split words
        words = re.findall(r'\b\w+\b', transcript.lower())
        total_words = len(words)
        
        # Count fillers
        total_fillers = 0
        filler_list = []
        for filler in filler_words:
            if ' ' in filler:  # Multi-word fillers like 'you know'
                count = len(re.findall(r'\b' + re.escape(filler) + r'\b', transcript.lower()))
                if count > 0:
                    total_fillers += count
                    filler_list.append(filler)
            else:
                count = words.count(filler)
                if count > 0:
                    total_fillers += count
                    filler_list.append(filler)
        
        # Calculate WPM (assuming 1 minute = 150 words average speaking rate)
        # Or use actual time if available - for now we estimate
        # 1 minute of speech ≈ 150 words
        estimated_minutes = max(1, total_words / 150)
        words_per_minute = int(total_words / estimated_minutes)
        
        # Calculate filler words per minute
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
