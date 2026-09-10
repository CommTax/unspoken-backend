from app.services.gemini_client import call_gemini_api
from app.services.signal_analyzer import analyze_signals, compute_impact_score
from app.utils.scenarios import SCENARIOS, PERSONA_MAP
from app.utils.helpers import generate_mock_deep_analysis, determine_emerging_persona
from app.models.schemas import (
    PremiumCommunicationAnalysisRequest,
    AnalysisMode,
    QuestionType
)
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import logging
import asyncio

logger = logging.getLogger(__name__)


class AnalysisService:
    """Service for communication analysis"""

    def __init__(self):
        self.scenarios = SCENARIOS
        self.persona_map = PERSONA_MAP

    # ============================================================
    # EXISTING METHOD - Deep Analysis (Preserved for /analyze endpoint)
    # ============================================================

    async def analyze_communication_deep(self, scenario_id: int, attempts_data: list):
        """
        Deep communication analysis using the Unspoken AI Analyst.
        Used by the /analyze endpoint (legacy front-page testing).
        """
        try:
            scenario = self.scenarios[scenario_id] if scenario_id < len(self.scenarios) else self.scenarios[0]

            results = []
            previous_responses = []

            for attempt in attempts_data:
                attempt_num = attempt.get('attempt', 1)
                response_text = attempt.get('response', '')
                mode = attempt.get('mode', 'text')

                print(f"\n📝 Analyzing Attempt {attempt_num}...")
                print(f"   Response: {response_text[:100]}...")

                prompt = self._build_deep_analysis_prompt(
                    scenario_id, response_text, attempt_num,
                    len(attempts_data), previous_responses
                )

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
                        'attempt': attempt_num, 'mode': mode, 'response': response_text,
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
                previous_responses.append({'attempt': attempt_num, 'response': response_text})

            dims = ['clarity', 'precision', 'structure', 'impact', 'influence']
            overall_scores = {d: 0 for d in dims}
            for result in results:
                scores = result.get('scores', {})
                for d in dims:
                    overall_scores[d] += scores.get(d, 50)
            for d in dims:
                overall_scores[d] = round(overall_scores[d] / len(results), 2)

            best_attempt = max(results, key=lambda x: sum(x.get('scores', {}).values()) / 5 if x.get('scores') else 0)
            is_complete = len(results) >= 3

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

    def _build_deep_analysis_prompt(self, scenario_id: int, response_text: str,
                                    attempt: int, total_attempts: int,
                                    previous_responses: list = None):
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
    # NEW DETERMINISTIC-FIRST ANALYSIS
    # ============================================================

    async def analyze_deterministic(
        self,
        transcript: str,
        duration_seconds: float,
        segments: Optional[List[Dict[str, Any]]] = None,
        question_type: str = "intro",
    ) -> Dict[str, Any]:
        """
        Deterministic-first communication analysis.

        Steps:
        1. Compute all signals locally (no LLM) — instant
        2. Compute impact score from signals (no LLM) — instant
        3. ONE LLM call for qualitative parts (pattern, gap, coaching, rewrite)
        4. Combine and return
        """
        try:
            logger.info(f"🔍 Deterministic analysis for: {transcript[:50]}...")

            # ─── Step 1: Deterministic signals ───
            signals = analyze_signals(
                transcript=transcript,
                duration_seconds=duration_seconds,
                segments=segments,
            )

            # ─── Step 2: Deterministic impact score ───
            impact_score = compute_impact_score(signals)

            # ─── Step 3: LLM for qualitative parts ───
            qualitative = await self._get_qualitative_analysis(
                transcript=transcript,
                signals=signals,
                impact_score=impact_score,
                question_type=question_type,
            )

            # ─── Step 4: Combine ───
            return {
                "success": True,
                "transcript": transcript,
                "signals": signals,
                "metrics": {
                    "impact": impact_score,
                },
                "diagnosis": {
                    "pattern_name": qualitative.get("pattern_name", "The Communicator"),
                    "pattern_description": qualitative.get("pattern_description", ""),
                },
                "gap": {
                    "what_got_lost": qualitative.get("what_got_lost", ""),
                    "unspoken_gap": qualitative.get("unspoken_gap", ""),
                },
                "coaching": {
                    "one_thing_to_change": qualitative.get("one_thing_to_change", "Lead with the point."),
                    "executive_version": qualitative.get("executive_version", ""),
                },
                # Legacy field name (frontend expects it)
                "before_after_rewrite": {
                    "executive_version": qualitative.get("executive_version", ""),
                },
            }

        except Exception as e:
            logger.error(f"❌ Deterministic analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return self._get_deterministic_fallback(transcript, duration_seconds)

    async def _get_qualitative_analysis(
        self,
        transcript: str,
        signals: Dict[str, Any],
        impact_score: int,
        question_type: str,
    ) -> Dict[str, Any]:
        """
        Single LLM call for qualitative parts.
        Receives deterministic signals as context so it can reference them.
        """
        prompt = self._build_qualitative_prompt(transcript, signals, impact_score, question_type)

        try:
            # Run blocking Gemini call in a thread with timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(call_gemini_api, prompt),
                timeout=20.0,
            )
            if isinstance(result, str):
                result = json.loads(result)
            if not isinstance(result, dict):
                raise ValueError("Invalid LLM response shape")
            return result
        except Exception as e:
            logger.warning(f"LLM qualitative call failed: {e}")
            return self._fallback_qualitative(signals)

    def _build_qualitative_prompt(
        self,
        transcript: str,
        signals: Dict[str, Any],
        impact_score: int,
        question_type: str,
    ) -> str:
        """Build the LLM prompt with signals as context."""
        context = ("introduce themselves professionally"
                   if question_type == "intro"
                   else "describe a current project")

        filler_summary = ", ".join(
            f"{w} ({c}x)" for w, c in signals["filler_words"]["breakdown"].items()
        ) or "none"

        return f"""You are The Unspoken AI Analyst - a communication expert.

The user was asked to {context}.

**Transcript:** "{transcript}"

**Signals already measured (do NOT recompute these):**
- Word count: {signals['word_count']}
- Speaking pace: {signals['words_per_minute']} wpm
- Filler words: {signals['filler_words']['total']} ({signals['filler_words']['percentage']}%) — {filler_summary}
- Sentences: {signals['sentences']['total']} total, avg {signals['sentences']['average_length']} words each
- Structural markers found: {', '.join(signals['structural_markers']['found']) or 'none'}
- Structural categories missing: {', '.join(signals['structural_markers']['missing']) or 'none'}
- Main point delay: ~{signals['main_point_delay_seconds']}s
- Rambling score: {signals['rambling_score']}/100
- Impact score: {impact_score}/100

**Use these signals to UNDERSTAND the pattern — but do NOT quote them verbatim. They inform your insight; they are not the insight itself.**

**Provide ONLY these 6 fields in JSON:**

{{
  "pattern_name": "Short memorable name like 'The Amplifier' or 'The Rambler'",
  "pattern_description": "ONE clean human sentence (max 20 words) describing the behavioral pattern — no stats, no numbers",
  "what_got_lost": "1 sentence — what was lost between intent and delivery (human language, not stats)",
  "unspoken_gap": "1 sentence — the gap between what they meant and what landed (human language, not stats)",
  "one_thing_to_change": "1 short imperative — the single most impactful change",
  "executive_version": "EXACTLY 1 SENTENCE — their response rewritten as a confident executive summary"
}}

RULES:
1. pattern_description: ONE clean sentence about the COMMUNICATION BEHAVIOR. No raw stats (word count, wpm, delays). No quoted numbers. Let the numbers shape your understanding — then speak to the human pattern.
2. what_got_lost and unspoken_gap: 1 sentence each. Human insight, not stats.
3. one_thing_to_change: 1 short imperative
4. executive_version: MUST be exactly 1 sentence
5. Be specific to THIS transcript, not generic
6. Return ONLY valid JSON. No other text.

JSON:"""

    def _fallback_qualitative(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback if LLM fails — human-language descriptions, no stats."""
        filler_pct = signals["filler_words"]["percentage"]
        rambling = signals["rambling_score"]
        duration = signals.get("duration_seconds", 30)
        delay = signals.get("main_point_delay_seconds", 0)

        if rambling > 60:
            pattern_name = "The Rambler"
            pattern_desc = "Your ideas circle before they land — you keep adding context instead of committing to the point."
        elif duration > 0 and delay > duration * 0.5:
            pattern_name = "The Amplifier"
            pattern_desc = "You pre-justify before making your point, softening your authority in the opening."
        elif filler_pct > 6:
            pattern_name = "The Hedger"
            pattern_desc = "You qualify your statements with filler words, which softens your authority."
        else:
            pattern_name = "The Communicator"
            pattern_desc = "You get your point across but could tighten the delivery for more impact."

        return {
            "pattern_name": pattern_name,
            "pattern_description": pattern_desc,
            "what_got_lost": "Your credibility and authority in the first 10 seconds.",
            "unspoken_gap": "Between your intent to sound confident and how you actually land.",
            "one_thing_to_change": "Lead with the point.",
            "executive_version": "I bring strategic clarity and results-driven leadership to every challenge.",
        }

    def _get_deterministic_fallback(
        self,
        transcript: str,
        duration_seconds: float,
    ) -> Dict[str, Any]:
        """Complete fallback if everything fails."""
        signals = analyze_signals(transcript, duration_seconds)
        impact_score = compute_impact_score(signals)
        qualitative = self._fallback_qualitative(signals)
        return {
            "success": True,
            "transcript": transcript,
            "signals": signals,
            "metrics": {"impact": impact_score},
            "diagnosis": {
                "pattern_name": qualitative["pattern_name"],
                "pattern_description": qualitative["pattern_description"],
            },
            "gap": {
                "what_got_lost": qualitative["what_got_lost"],
                "unspoken_gap": qualitative["unspoken_gap"],
            },
            "coaching": {
                "one_thing_to_change": qualitative["one_thing_to_change"],
                "executive_version": qualitative["executive_version"],
            },
            "before_after_rewrite": {
                "executive_version": qualitative["executive_version"],
            },
        }


# ============================================================
# FACTORY
# ============================================================

def get_analysis_service():
    """Factory function to get AnalysisService instance"""
    return AnalysisService()
