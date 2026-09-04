import os
import asyncpg
import re
import random
import string
import hashlib
import secrets
from app.utils.scenarios import SCENARIOS, PERSONA_MAP

# ============================================================
# DATABASE HELPERS
# ============================================================

async def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("⚠️ DATABASE_URL not configured. Database features disabled.")
        return None
    
    if database_url.startswith("postgresql://"):
        match = re.search(r'@([^:/]+)(?=/)', database_url)
        if match:
            host = match.group(1)
            if f"@{host}/" in database_url:
                database_url = database_url.replace(f"@{host}/", f"@{host}:5432/")
    
    try:
        conn = await asyncpg.connect(dsn=database_url)
        print("✅ PostgreSQL connection successful")
        return conn
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return None

# ============================================================
# PASSWORD HELPERS
# ============================================================

def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=12))

def hash_password(password: str):
    salt = secrets.token_hex(16)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() + ':' + salt

def verify_password(password: str, hashed: str):
    try:
        stored_hash, salt = hashed.split(':')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
        return new_hash == stored_hash
    except:
        return False

# ============================================================
# MOCK ANALYSIS HELPERS
# ============================================================

def generate_mock_deep_analysis(text: str, scenario_id: int = 0):
    """Generate a mock deep analysis for fallback."""
    
    scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
    
    # Determine basic quality indicators
    word_count = len(text.split())
    has_numbers = bool(re.search(r'\d', text))
    has_clear_ask = bool(re.search(r'\?|please|recommend|suggest|propose|request', text, re.IGNORECASE))
    has_confidence = bool(re.search(r'I believe|I know|I\'m confident|I\'m sure|I think', text, re.IGNORECASE))
    has_impact = bool(re.search(r'deliver|achieve|result|outcome|success|goal', text, re.IGNORECASE))
    
    random.seed(hash(text) % 10000)
    
    scores = {
        'clarity': min(92, max(35, 45 + (20 if has_clear_ask else 0) + (8 if word_count > 15 else 0) + random.randint(-7, 7))),
        'precision': min(92, max(30, 40 + (25 if has_numbers else 0) + (8 if word_count > 20 else 0) + random.randint(-7, 7))),
        'structure': min(92, max(25, 35 + (30 if has_clear_ask else 0) + random.randint(-7, 7))),
        'impact': min(92, max(30, 40 + (20 if has_impact else 0) + (12 if has_clear_ask else 0) + random.randint(-7, 7))),
        'influence': min(92, max(25, 35 + (22 if has_confidence else 0) + (18 if has_clear_ask else 0) + random.randint(-7, 7)))
    }
    
    # Scenario-specific analysis
    if scenario_id == 0:  # Deadline
        analysis = {
            "what_you_meant": "You wanted to explain the deadline situation and show you're taking responsibility",
            "what_landed": "The listener likely heard uncertainty and lack of a concrete solution",
            "what_got_lost": "Your confidence, specific plan, and accountability got lost",
            "the_unspoken_gap": "Between taking responsibility and showing you have it under control",
            "why_it_matters": "This affects trust and confidence in your ability to deliver",
            "one_thing_to_change": "Start with the solution, not the problem",
            "behavioral_evidence": [
                "You mention the problem but don't lead with a solution",
                "Vague timeline references instead of specific dates",
                "No mention of lessons learned or prevention"
            ],
            "patterns_detected": [
                "Tendency to explain rather than solve",
                "Under-communicating accountability",
                "Missing action-oriented language"
            ]
        }
    elif scenario_id == 4:  # Interview
        analysis = {
            "what_you_meant": "You wanted to present yourself as a capable, enthusiastic candidate",
            "what_landed": "The interviewer likely heard uncertainty and lack of clarity",
            "what_got_lost": "Your specific achievements, passion, and value proposition got lost",
            "the_unspoken_gap": "Between having potential and communicating it effectively",
            "why_it_matters": "This is your only chance to make a first impression",
            "one_thing_to_change": "Structure: Who you are → What you've done → Why you're a fit",
            "behavioral_evidence": [
                "No clear opening statement about who you are",
                "Vague descriptions of experience",
                "No closing statement about why you want the role"
            ],
            "patterns_detected": [
                "Under-communicating achievements",
                "Lack of storytelling structure",
                "Missing enthusiasm indicators"
            ]
        }
    else:
        analysis = {
            "what_you_meant": "You wanted to communicate your message effectively",
            "what_landed": "The listener may have missed the full meaning",
            "what_got_lost": "Some nuance and impact got lost in the delivery",
            "the_unspoken_gap": "Between your intention and the perceived message",
            "why_it_matters": "This affects how your message is received",
            "one_thing_to_change": "Make your core message more prominent",
            "behavioral_evidence": [
                "Your main point could be stated more directly",
                "Supporting details could be more specific",
                "The call to action could be clearer"
            ],
            "patterns_detected": [
                "Good intent but delivery needs refinement",
                "Potential to be more impactful"
            ]
        }
    
    return {
        'scores': scores,
        **analysis,
        'what_you_said': text,
        'better_version': generate_better_version(text, scenario_id),
        'why_better': [
            "Clear structure makes it easy to follow",
            "Specific details add credibility",
            "Strong closing leaves a lasting impression"
        ]
    }

def generate_better_version(text: str, scenario_id: int):
    """Generate an improved version based on the scenario."""
    
    better_versions = {
        0: "The deadline delay was caused by an unexpected technical dependency. I've already identified the bottleneck and we're implementing a solution. I'll have a detailed recovery plan ready within 30 minutes with a revised timeline. We're committed to delivering quality work.",
        1: "I understand your budget concerns. Let me show you the ROI - our solution typically saves 30% on operational costs in year one. We also offer flexible payment options and a phased rollout. Would you like me to walk you through the specific savings for your team?",
        2: "I believe I've earned this promotion. Over the past year, I've exceeded targets by 20%, led two successful product launches, and mentored three team members. I'm ready to take on more strategic ownership and contribute at a higher level.",
        3: "I'd like to discuss your recent performance constructively. I've noticed some quality issues and missed deadlines. I know you're capable of great work - what support do you need from me to get back on track? Let's work together to improve.",
        4: "I'm a passionate problem-solver with strong SQL skills and a drive to learn. During my studies, I completed several database projects and helped my team implement a data analytics solution. I'm excited to bring this energy to your team and grow as a professional."
    }
    
    return better_versions.get(scenario_id, better_versions[4])

def determine_emerging_persona(attempts_data: list, persona_map: dict):
    """Determine the emerging persona based on all attempts."""
    if len(attempts_data) < 3:
        return None
    
    dims = ['clarity', 'precision', 'structure', 'impact', 'influence']
    totals = {d: 0 for d in dims}
    
    for attempt in attempts_data:
        scores = attempt.get('scores', {})
        for d in dims:
            totals[d] += scores.get(d, 50)
    
    strongest = max(totals, key=totals.get)
    weakest = min(totals, key=totals.get)
    
    persona = persona_map.get(strongest, persona_map['clarity'])
    
    return {
        'persona': persona,
        'strongest': strongest.upper(),
        'weakest': weakest.upper()
    }
