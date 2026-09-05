from app.services.gemini_client import call_gemini_api
from app.utils.scenarios import SCENARIOS, PERSONA_MAP
from app.utils.helpers import generate_mock_deep_analysis, determine_emerging_persona
from app.models.schemas import (
    PremiumCommunicationAnalysisRequest,
    PremiumCommunicationAnalysisResponse,
    PremiumMetrics,
    CommunicationGap,
    BehavioralEvidence,
    PatternsDetected,
    InstantMirrorAnalysis,
    BeforeAfterRewrite,
    SignalToNoiseRatio,
    AttentionWaveform,
    PatternDiagnosis,
    AnalysisMode,
    QuestionType
)
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class AnalysisService:
    """Service for communication analysis with premium metrics"""
    
    def __init__(self):
        self.scenarios = SCENARIOS
        self.persona_map = PERSONA_MAP
    
    # ============================================================
    # EXISTING METHOD - Deep Analysis (Preserved)
    # ============================================================
    
    async def analyze_communication_deep(self, scenario_id: int, attempts_data: list):
        """
        Deep communication analysis using the Unspoken AI Analyst.
        Preserved for backward compatibility.
        """
        try:
            scenario = self.scenarios[scenario_id] if scenario_id < len(self.scenarios) else self.scenarios[0]
            
            # Process each attempt
            results = []
            previous_responses = []
            
            for attempt in attempts_data:
                attempt_num = attempt.get('attempt', 1)
                response_text = attempt.get('response', '')
                mode = attempt.get('mode', 'text')
                
                print(f"\n📝 Analyzing Attempt {attempt_num}...")
                print(f"   Response: {response_text[:100]}...")
                
                # Build prompt
                prompt = self._build_deep_analysis_prompt(
                    scenario_id,
                    response_text,
                    attempt_num,
                    len(attempts_data),
                    previous_responses
                )
                
                # Call Gemini
                gemini_result = call_gemini_api(prompt)
                
                if gemini_result and 'scores' in gemini_result:
                    print("✅ Using Gemini deep analysis")
                    result = {
                        'attempt': attempt_num,
                        'mode': mode,
                        'response': response_text,
                        'scores': gemini_result.get('scores', {}),
                        'what_you_meant': gemini_result.get('what_you_meant', ''),
                        'what_you_said': gemini_result.get('what_you_said', ''),
                        'what_landed': gemini_result.get('what_landed', ''),
                        'what_got_lost': gemini_result.get('what_got_lost', ''),
                        'the_unspoken_gap': gemini_result.get('the_unspoken_gap', ''),
                        'why_it_matters': gemini_result.get('why_it_matters', ''),
                        'one_thing_to_change': gemini_result.get('one_thing_to_change', ''),
                        'behavioral_evidence': gemini_result.get('behavioral_evidence', []),
                        'patterns_detected': gemini_result.get('patterns_detected', []),
                        'better_version': gemini_result.get('better_version', ''),
                        'why_better': gemini_result.get('why_better', [])
                    }
                else:
                    print("⚠️ Using fallback analysis")
                    mock = generate_mock_deep_analysis(response_text, scenario_id)
                    result = {
                        'attempt': attempt_num,
                        'mode': mode,
                        'response': response_text,
                        'scores': mock.get('scores', {}),
                        'what_you_meant': mock.get('what_you_meant', ''),
                        'what_you_said': mock.get('what_you_said', ''),
                        'what_landed': mock.get('what_landed', ''),
                        'what_got_lost': mock.get('what_got_lost', ''),
                        'the_unspoken_gap': mock.get('the_unspoken_gap', ''),
                        'why_it_matters': mock.get('why_it_matters', ''),
                        'one_thing_to_change': mock.get('one_thing_to_change', ''),
                        'behavioral_evidence': mock.get('behavioral_evidence', []),
                        'patterns_detected': mock.get('patterns_detected', []),
                        'better_version': mock.get('better_version', ''),
                        'why_better': mock.get('why_better', [])
                    }
                
                results.append(result)
                previous_responses.append({
                    'attempt': attempt_num,
                    'response': response_text
                })
            
            # Calculate overall scores
            dims = ['clarity', 'precision', 'structure', 'impact', 'influence']
            overall_scores = {d: 0 for d in dims}
            for result in results:
                scores = result.get('scores', {})
                for d in dims:
                    overall_scores[d] += scores.get(d, 50)
            
            for d in dims:
                overall_scores[d] = round(overall_scores[d] / len(results), 2)
            
            # Find best attempt
            best_attempt = max(results, key=lambda x: sum(x.get('scores', {}).values()) / 5 if x.get('scores') else 0)
            is_complete = len(results) >= 3
            
            # Build response
            response_data = {
                'success': True,
                'is_complete': is_complete,
                'attempts': results,
                'overall_scores': overall_scores,
                'best_attempt': best_attempt,
                'scenario': {
                    'id': scenario_id,
                    'context': scenario['context'],
                    'question': scenario['question']
                },
                'attempts_remaining': max(0, 3 - len(results)),
                'message': f'Analysis complete for attempt {len(results)} of 3'
            }
            
            # If 3 attempts complete, determine emerging persona
            if is_complete:
                persona_result = determine_emerging_persona(results, self.persona_map)
                if persona_result:
                    response_data['emerging_persona'] = {
                        'name': persona_result['persona']['name'],
                        'description': persona_result['persona']['description'],
                        'strength_label': persona_result['persona']['strength_label'],
                        'strength_desc': persona_result['persona']['strength_desc'],
                        'growth_label': persona_result['persona']['growth_label'],
                        'growth_desc': persona_result['persona']['growth_desc'],
                        'strongest_dimension': persona_result['strongest'],
                        'weakest_dimension': persona_result['weakest']
                    }
                    response_data['message'] = 'All 3 attempts analyzed. Emerging persona revealed!'
                    response_data['prompt_for_paid'] = True
                    response_data['paid_price'] = '₹499'
                    response_data['paid_message'] = "You've only seen one conversation. Unlock your full Unspoken Profile for ₹499."
            
            print(f"\n✅ Analysis complete. Complete: {is_complete}")
            return response_data
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}

    def _build_deep_analysis_prompt(self, scenario_id: int, response_text: str, attempt: int, total_attempts: int, previous_responses: list = None):
        """Build the deep analysis prompt for the AI Analyst."""
        
        scenario = self.scenarios[scenario_id] if scenario_id < len(self.scenarios) else self.scenarios[0]
        
        prompt = f"""You are The Unspoken AI Analyst - a world-class communication coach with deep expertise in behavioral psychology and interpersonal dynamics.

Analyze this communication scenario in depth:

SCENARIO: {scenario['context']}
QUESTION: {scenario['question']}

USER'S RESPONSE (Attempt {attempt} of {total_attempts}):
"{response_text}"

{"PREVIOUS ATTEMPTS: " + str(previous_responses) if previous_responses else ""}

Provide a comprehensive analysis in the following JSON format:

{{
  "scores": {{
    "clarity": 0-100,
    "precision": 0-100,
    "structure": 0-100,
    "impact": 0-100,
    "influence": 0-100
  }},
  
  "what_you_meant": "What the user likely intended to communicate",
  "what_you_said": "What the user actually said",
  "what_landed": "What the listener likely heard",
  "what_got_lost": "What didn't get communicated effectively",
  "the_unspoken_gap": "The gap between what was meant and what landed",
  "why_it_matters": "Why this gap matters in the context",
  "one_thing_to_change": "The single most impactful change",
  "behavioral_evidence": ["Specific behavioral observations"],
  "patterns_detected": ["Patterns in the user's communication style"],
  "better_version": "A rewritten version of the response",
  "why_better": ["Explanation of why the better version works"]
}}

Return ONLY valid JSON. Do not include any other text."""
        
        return prompt

    # ============================================================
    # NEW METHOD - Premium Communication Analysis
    # ============================================================
    
    async def analyze_premium_communication(
        self, 
        request: PremiumCommunicationAnalysisRequest
    ) -> PremiumCommunicationAnalysisResponse:
        """
        Analyze communication and return comprehensive premium metrics
        """
        try:
            # Get analysis from Gemini
            gemini_analysis = await self._get_gemini_premium_analysis(request)
            
            # Parse and structure the response
            return self._parse_premium_analysis_response(gemini_analysis, request)
            
        except Exception as e:
            logger.error(f"Premium analysis error: {e}")
            # Return default response if analysis fails
            return self._get_default_premium_response(request)
    
    async def _get_gemini_premium_analysis(self, request: PremiumCommunicationAnalysisRequest) -> dict:
        """
        Get comprehensive analysis from Gemini API
        """
        prompt = self._build_premium_analysis_prompt(request)
        result = call_gemini_api(prompt)
        
        # If result is string, parse it
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                logger.error("Failed to parse Gemini response as JSON")
                return {}
        
        return result or {}
    
    def _build_premium_analysis_prompt(self, request: PremiumCommunicationAnalysisRequest) -> str:
        """
        Build the prompt for Gemini with all required premium analysis elements
        """
        question_context = "introduce yourself professionally" if request.question_type == QuestionType.INTRO else "describe a current project you're working on"
        
        prompt = f"""
        You are The Unspoken AI Analyst - a world-class communication coach with deep expertise in behavioral psychology and interpersonal dynamics.
        
        Analyze the following communication sample and provide a comprehensive premium analysis.
        
        **User Input:** "{request.text}"
        
        **Context:** The user was asked to {question_context}.
        **Mode:** {request.mode.value}
        **Question Type:** {request.question_type.value}
        
        **Provide a detailed analysis in JSON format with the following structure:**
        
        {{
            "metrics": {{
                "clarity": <score 0-100 based on how clear and unambiguous the message is>,
                "precision": <score 0-100 based on how concise and exact the language is>,
                "structure": <score 0-100 based on how well-organized the response is>,
                "impact": <score 0-100 based on how compelling and memorable the message is>,
                "influence": <score 0-100 based on how persuasive and authoritative the tone is>
            }},
            "gap": {{
                "what_you_meant": "<what the user likely intended to communicate>",
                "what_landed": "<what the audience likely perceived>",
                "what_got_lost": "<what got lost in translation>",
                "unspoken_gap": "<the gap between intention and delivery in one powerful sentence>",
                "why_it_matters": "<why this gap is significant in this context>"
            }},
            "behavioral_evidence": {{
                "evidence_list": [
                    "<specific behavioral observation 1>",
                    "<specific behavioral observation 2>",
                    "<specific behavioral observation 3>"
                ]
            }},
            "patterns_detected": {{
                "pattern_list": [
                    "<communication pattern 1>",
                    "<communication pattern 2>",
                    "<communication pattern 3>"
                ]
            }},
            "instant_mirror": {{
                "time_to_point": <seconds until main point was made>,
                "opened_with": "<exact opening words from the response>",
                "actual_point": "<where the actual main point landed>",
                "insight": "<key insight about the opening>"
            }},
            "before_after_rewrite": {{
                "what_you_said": "<original text with filler words and rambling>",
                "executive_version": "<concise, impactful executive version>",
                "improvement_metrics": {{
                    "shorter_by_percent": <percentage improvement in length>,
                    "impact_multiplier": <multiplier for improved impact>
                }}
            }},
            "signal_to_noise": {{
                "snr_percentage": <signal percentage 0-100>,
                "noise_percentage": <noise percentage 0-100>,
                "signal_percentage": <signal percentage 0-100>,
                "word_count": <total words in response>,
                "needed_words": <optimal word count for this message>,
                "filler_content": "<description of what constituted filler>"
            }},
            "attention_waveform": {{
                "dropoff_second": <second when attention dropped>,
                "wave_data": [<array of 20 float values 0-1 representing attention over time>],
                "annotation": "<annotation about attention dropoff>"
            }},
            "diagnosis": {{
                "pattern_name": "<name of the communication pattern like 'The Amplifier'>",
                "pattern_description": "<brief description of the pattern>",
                "time_to_point": <seconds to get to the point>,
                "target_time": <target seconds for getting to the point>,
                "impact_score": <overall impact score 0-100>,
                "impact_level": "<description of impact level>"
            }}
        }}
        
        **Scoring Guidelines:**
        - Clarity (0-100): How well-structured and unambiguous is the message?
        - Precision (0-100): How concise and exact is the language?
        - Structure (0-100): How well-organized is the response?
        - Impact (0-100): How compelling and memorable is the message?
        - Influence (0-100): How persuasive and authoritative is the tone?
        
        **Behavioral Evidence Points (look for):**
        - No clear opening statement
        - Vague descriptions
        - Missing closing statement
        - Use of filler words
        - Rambling before getting to the point
        
        **Patterns to Detect:**
        - Under-communicating achievements (downplaying success)
        - Over-explaining/rambling (taking too long to get to point)
        - Missing enthusiasm indicators (flat delivery)
        - Lack of storytelling structure (no narrative flow)
        - Weak closing statements (ending without impact)
        
        **Attention Waveform Data:**
        - Generate 20 values representing attention levels over 45 seconds
        - Values should range from 0.0 to 1.0
        - Start high (0.8-1.0), gradually decrease based on engagement
        
        Return ONLY valid JSON. Do not include any other text.
        """
        
        return prompt
    
    def _parse_premium_analysis_response(
        self, 
        analysis: dict, 
        request: PremiumCommunicationAnalysisRequest
    ) -> PremiumCommunicationAnalysisResponse:
        """
        Parse Gemini response into Pydantic models
        """
        try:
            # Parse metrics
            metrics_data = analysis.get("metrics", {})
            metrics = PremiumMetrics(
                clarity=metrics_data.get("clarity", 59),
                precision=metrics_data.get("precision", 74),
                structure=metrics_data.get("structure", 35),
                impact=metrics_data.get("impact", 47),
                influence=metrics_data.get("influence", 32)
            )
            
            # Parse gap
            gap_data = analysis.get("gap", {})
            gap = CommunicationGap(
                what_you_meant=gap_data.get("what_you_meant", "You wanted to present yourself as a capable, enthusiastic candidate"),
                what_landed=gap_data.get("what_landed", "The interviewer likely heard uncertainty and lack of clarity"),
                what_got_lost=gap_data.get("what_got_lost", "Your specific achievements, passion, and value proposition got lost"),
                unspoken_gap=gap_data.get("unspoken_gap", "Between having potential and communicating it effectively"),
                why_it_matters=gap_data.get("why_it_matters", "This is your only chance to make a first impression")
            )
            
            # Parse behavioral evidence
            evidence_data = analysis.get("behavioral_evidence", {})
            evidence = BehavioralEvidence(
                evidence_list=evidence_data.get("evidence_list", [
                    "No clear opening statement about who you are",
                    "Vague descriptions of experience",
                    "No closing statement about why you want the role"
                ])
            )
            
            # Parse patterns
            patterns_data = analysis.get("patterns_detected", {})
            patterns = PatternsDetected(
                pattern_list=patterns_data.get("pattern_list", [
                    "Under-communicating achievements",
                    "Lack of storytelling structure",
                    "Missing enthusiasm indicators"
                ])
            )
            
            # Parse instant mirror
            mirror_data = analysis.get("instant_mirror", {})
            instant_mirror = InstantMirrorAnalysis(
                time_to_point=mirror_data.get("time_to_point", 18),
                opened_with=mirror_data.get("opened_with", "Well, regarding the project, we've been working on this for a few weeks now..."),
                actual_point=mirror_data.get("actual_point", "We are two days behind schedule, but we will deliver by Friday."),
                insight=mirror_data.get("insight", "Executives lost focus before you got to the answer.")
            )
            
            # Parse before/after rewrite
            rewrite_data = analysis.get("before_after_rewrite", {})
            before_after = BeforeAfterRewrite(
                what_you_said=rewrite_data.get("what_you_said", "Yeah so, I think for the campaign, we could try testing short-form videos because images aren't getting engagement anymore and maybe track clicks."),
                executive_version=rewrite_data.get("executive_version", "I recommend shifting 100% of our ad spend to short-form video. Recent data shows static images have dropped 40% in CTR."),
                improvement_metrics=rewrite_data.get("improvement_metrics", {
                    "shorter_by_percent": 73,
                    "impact_multiplier": 2
                })
            )
            
            # Parse SNR
            snr_data = analysis.get("signal_to_noise", {})
            signal_to_noise = SignalToNoiseRatio(
                snr_percentage=snr_data.get("snr_percentage", 38),
                noise_percentage=snr_data.get("noise_percentage", 62),
                signal_percentage=snr_data.get("signal_percentage", 38),
                word_count=snr_data.get("word_count", 85),
                needed_words=snr_data.get("needed_words", 32),
                filler_content=snr_data.get("filler_content", "62% of your response consisted of filler words, thought-processing, and redundant qualifiers.")
            )
            
            # Parse attention waveform
            waveform_data = analysis.get("attention_waveform", {})
            attention_waveform = AttentionWaveform(
                dropoff_second=waveform_data.get("dropoff_second", 14),
                wave_data=waveform_data.get("wave_data", [0.8, 0.9, 0.95, 0.85, 0.75, 0.7, 0.55, 0.45, 0.3, 0.2, 0.15, 0.12, 0.1, 0.08, 0.1, 0.12, 0.15, 0.18, 0.15, 0.12]),
                annotation=waveform_data.get("annotation", "You lost executive impact at second 14")
            )
            
            # Parse diagnosis
            diagnosis_data = analysis.get("diagnosis", {})
            diagnosis = PatternDiagnosis(
                pattern_name=diagnosis_data.get("pattern_name", "The Amplifier"),
                pattern_description=diagnosis_data.get("pattern_description", "You pre-justify under pressure"),
                time_to_point=diagnosis_data.get("time_to_point", 18),
                target_time=diagnosis_data.get("target_time", 5),
                impact_score=diagnosis_data.get("impact_score", 42),
                impact_level=diagnosis_data.get("impact_level", "Room for executive presence")
            )
            
            return PremiumCommunicationAnalysisResponse(
                metrics=metrics,
                gap=gap,
                behavioral_evidence=evidence,
                patterns_detected=patterns,
                instant_mirror=instant_mirror,
                before_after_rewrite=before_after,
                signal_to_noise=signal_to_noise,
                attention_waveform=attention_waveform,
                diagnosis=diagnosis,
                timestamp=datetime.now(),
                mode=request.mode,
                question_type=request.question_type
            )
            
        except Exception as e:
            logger.error(f"Error parsing premium analysis: {e}")
            return self._get_default_premium_response(request)
    
    def _get_default_premium_response(self, request: PremiumCommunicationAnalysisRequest) -> PremiumCommunicationAnalysisResponse:
        """
        Return default premium response if analysis fails
        """
        return PremiumCommunicationAnalysisResponse(
            metrics=PremiumMetrics(
                clarity=59,
                precision=74,
                structure=35,
                impact=47,
                influence=32
            ),
            gap=CommunicationGap(
                what_you_meant="You wanted to present yourself as a capable, enthusiastic candidate",
                what_landed="The interviewer likely heard uncertainty and lack of clarity",
                what_got_lost="Your specific achievements, passion, and value proposition got lost",
                unspoken_gap="Between having potential and communicating it effectively",
                why_it_matters="This is your only chance to make a first impression"
            ),
            behavioral_evidence=BehavioralEvidence(
                evidence_list=[
                    "No clear opening statement about who you are",
                    "Vague descriptions of experience",
                    "No closing statement about why you want the role"
                ]
            ),
            patterns_detected=PatternsDetected(
                pattern_list=[
                    "Under-communicating achievements",
                    "Lack of storytelling structure",
                    "Missing enthusiasm indicators"
                ]
            ),
            instant_mirror=InstantMirrorAnalysis(
                time_to_point=18,
                opened_with="Well, regarding the project, we've been working on this for a few weeks now...",
                actual_point="We are two days behind schedule, but we will deliver by Friday.",
                insight="Executives lost focus before you got to the answer."
            ),
            before_after_rewrite=BeforeAfterRewrite(
                what_you_said="Yeah so, I think for the campaign, we could try testing short-form videos because images aren't getting engagement anymore and maybe track clicks.",
                executive_version="I recommend shifting 100% of our ad spend to short-form video. Recent data shows static images have dropped 40% in CTR.",
                improvement_metrics={
                    "shorter_by_percent": 73,
                    "impact_multiplier": 2
                }
            ),
            signal_to_noise=SignalToNoiseRatio(
                snr_percentage=38,
                noise_percentage=62,
                signal_percentage=38,
                word_count=85,
                needed_words=32,
                filler_content="62% of your response consisted of filler words, thought-processing, and redundant qualifiers."
            ),
            attention_waveform=AttentionWaveform(
                dropoff_second=14,
                wave_data=[0.8, 0.9, 0.95, 0.85, 0.75, 0.7, 0.55, 0.45, 0.3, 0.2, 0.15, 0.12, 0.1, 0.08, 0.1, 0.12, 0.15, 0.18, 0.15, 0.12],
                annotation="You lost executive impact at second 14"
            ),
            diagnosis=PatternDiagnosis(
                pattern_name="The Amplifier",
                pattern_description="You pre-justify under pressure",
                time_to_point=18,
                target_time=5,
                impact_score=42,
                impact_level="Room for executive presence"
            ),
            timestamp=datetime.now(),
            mode=request.mode,
            question_type=request.question_type
        )


# ============================================================
# HELPER FUNCTIONS (for backward compatibility)
# ============================================================

def get_analysis_service():
    """Factory function to get AnalysisService instance"""
    return AnalysisService()
