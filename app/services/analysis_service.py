from app.services.gemini_client import call_gemini_api
from app.utils.scenarios import SCENARIOS, PERSONA_MAP
from app.utils.helpers import generate_mock_deep_analysis, determine_emerging_persona

async def analyze_communication_deep(scenario_id: int, attempts_data: list):
    """
    Deep communication analysis using the Unspoken AI Analyst.
    """
    try:
        scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
        
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
            prompt = build_deep_analysis_prompt(
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
            persona_result = determine_emerging_persona(results, PERSONA_MAP)
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

def build_deep_analysis_prompt(scenario_id: int, response_text: str, attempt: int, total_attempts: int, previous_responses: list = None):
    """Build the deep analysis prompt for the AI Analyst."""
    
    scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
    
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
