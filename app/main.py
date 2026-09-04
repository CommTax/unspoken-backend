from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from dotenv import load_dotenv
import os
import asyncpg
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import re
import uuid
import json
import random
import string
import hashlib
import secrets
from datetime import datetime
import google.generativeai as genai

load_dotenv()

# ============================================================
# CREATE APP
# ============================================================

app = FastAPI(
    title="Unspoken Backend",
    description="Paid Persona Assessment + Communication Analysis",
    version="1.0.0"
)

# ============================================================
# CORS MIDDLEWARE
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://theunspoken.co.in",
        "https://www.theunspoken.co.in",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600
)

# ============================================================
# GEMINI API CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("⚠️ GEMINI_API_KEY not set. Using mock mode.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ Gemini API configured successfully")
    except Exception as e:
        print(f"⚠️ Gemini API configuration error: {e}")
        GEMINI_API_KEY = None

# ============================================================
# DATABASE CONNECTION
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
# HELPERS
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
# MODELS
# ============================================================

class LeadCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None


class UserCreate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None


class PersonaAssessmentRequest(BaseModel):
    user_details: UserCreate
    responses: List[dict]
    type: str = 'paid'


# Communication Analysis Models
class AttemptData(BaseModel):
    attempt: int
    response: str
    mode: str


class CommunicationRequest(BaseModel):
    scenario_id: int
    attempts: Optional[List[AttemptData]] = None
    response: Optional[str] = None
    attempt: Optional[int] = None
    mode: Optional[str] = None
    previous_attempts: Optional[List[Dict[str, Any]]] = None


# ============================================================
# SCENARIOS DATA
# ============================================================

SCENARIOS = [
    {
        "id": 0,
        "context": "Your team missed a key deadline. You need to update your manager.",
        "question": "Your manager asks: 'What happened with the deadline, and what's your plan to fix it?'"
    },
    {
        "id": 1,
        "context": "A client says your proposal is too expensive. You need to respond and keep the deal alive.",
        "question": "The client says: 'Your price is 30% higher than your competitor's. Why should we go with you?'"
    },
    {
        "id": 2,
        "context": "You want to ask your manager for a promotion. Draft your pitch.",
        "question": "Your manager says: 'Tell me why you deserve a promotion right now.'"
    },
    {
        "id": 3,
        "context": "You need to give constructive feedback to a teammate who's been underperforming.",
        "question": "Your teammate asks: 'Is there anything I could be doing better?'"
    },
    {
        "id": 4,
        "context": "You're in a job interview. The interviewer asks the classic opening question.",
        "question": "Interviewer: 'Tell me about yourself.'"
    }
]


# ============================================================
# PERSONA MAP
# ============================================================

PERSONA_MAP = {
    'clarity': {
        'name': 'The Translator',
        'description': 'You make complexity make sense.',
        'strength_label': 'CLARITY',
        'strength_desc': 'You tend to make your core message understandable once you commit to it.',
        'growth_label': 'INFLUENCE',
        'growth_desc': 'You explain your position well, but your strongest recommendation sometimes arrives too softly.'
    },
    'precision': {
        'name': 'The Articulator',
        'description': 'You speak with clarity and command.',
        'strength_label': 'PRECISION',
        'strength_desc': 'You use specific, concrete language that leaves little room for ambiguity.',
        'growth_label': 'INFLUENCE',
        'growth_desc': 'You can get so specific that you miss the bigger picture.'
    },
    'structure': {
        'name': 'The Architect',
        'description': 'You build ideas that stand firm.',
        'strength_label': 'STRUCTURE',
        'strength_desc': 'You organize your thoughts in a logical, easy-to-follow sequence.',
        'growth_label': 'IMPACT',
        'growth_desc': 'Your structure can become rigid, making you less adaptable in conversation.'
    },
    'impact': {
        'name': 'The Amplifier',
        'description': 'Your presence makes ideas unforgettable.',
        'strength_label': 'IMPACT',
        'strength_desc': 'Your messages have a lasting impression on those who hear them.',
        'growth_label': 'PRECISION',
        'growth_desc': 'Your strong delivery can sometimes overwhelm softer messages.'
    },
    'influence': {
        'name': 'The Catalyst',
        'description': 'You move people to action.',
        'strength_label': 'INFLUENCE',
        'strength_desc': 'You have a natural ability to persuade and move others to action.',
        'growth_label': 'STRUCTURE',
        'growth_desc': 'Your passion can sometimes outpace your structure.'
    }
}


# ============================================================
# PERSONA ASSESSMENT - SCORING ENGINE
# ============================================================

def calculate_competency_scores(responses):
    category_mapping = {
        'structure': ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6'],
        'thinking': ['Q7', 'Q8', 'Q9', 'Q10', 'Q11', 'Q12'],
        'impact': ['Q13', 'Q14', 'Q15', 'Q16', 'Q17', 'Q18'],
        'expression': ['Q19', 'Q20', 'Q21', 'Q22', 'Q23', 'Q24'],
        'connection': ['Q25', 'Q26', 'Q27', 'Q28', 'Q29', 'Q30']
    }
    
    competency_scores = {
        'structure': 0,
        'thinking': 0,
        'impact': 0,
        'expression': 0,
        'connection': 0
    }
    
    for r in responses:
        question_code = r.get('question_code')
        answer = r.get('answer')
        
        try:
            score = int(answer)
        except:
            continue
        
        for category, questions in category_mapping.items():
            if question_code in questions:
                competency_scores[category] += score
                break
    
    for category in competency_scores:
        competency_scores[category] = round((competency_scores[category] / 6) * 20, 2)
    
    return competency_scores


def get_score_range(score):
    if score >= 90:
        return '90-100'
    elif score >= 75:
        return '75-89'
    elif score >= 60:
        return '60-74'
    elif score >= 40:
        return '40-59'
    else:
        return 'Below 40'


def determine_persona_from_assessment(competency_scores):
    def get_level(score):
        if score >= 80: return 'high'
        if score >= 60: return 'mid'
        return 'low'
    
    levels = {cat: get_level(score) for cat, score in competency_scores.items()}
    
    if all(level == 'high' for level in levels.values()):
        return 'TRANSLATOR'
    elif levels['impact'] == 'high' and levels['expression'] == 'high':
        return 'AMPLIFIER'
    elif levels['structure'] == 'high' and levels['expression'] == 'high':
        return 'ARTICULATOR'
    elif levels['thinking'] == 'high' and levels['connection'] == 'high':
        return 'INTERPRETER'
    elif levels['thinking'] == 'high' and levels['structure'] == 'high' and levels['impact'] == 'low':
        return 'FILTER'
    elif levels['impact'] == 'low':
        other_levels = [levels[cat] for cat in ['structure', 'thinking', 'expression', 'connection']]
        if any(level == 'high' for level in other_levels) or all(level != 'low' for level in other_levels):
            return 'EMERGING'
    
    connection_score = competency_scores['connection']
    other_scores = [competency_scores[cat] for cat in ['structure', 'thinking', 'impact', 'expression']]
    avg_other = sum(other_scores) / len(other_scores) if other_scores else 0
    
    if connection_score < avg_other - 15:
        return 'MISALIGNED'
    
    return 'ARTICULATOR'


async def get_competency_writeups(conn, competency_scores):
    writeups = {}
    
    for competency, score in competency_scores.items():
        score_range = get_score_range(score)
        
        if conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    competency,
                    score_range,
                    category,
                    executive_narrative,
                    whats_working,
                    whats_holding_you_back,
                    how_others_experience_you,
                    professional_impact,
                    highest_roi_improvement
                FROM competency_scores
                WHERE competency = $1 AND score_range = $2
                """,
                competency, score_range
            )
            
            if row:
                writeups[competency] = {
                    'score': score,
                    'score_range': row['score_range'],
                    'category': row['category'],
                    'executive_narrative': row['executive_narrative'],
                    'whats_working': row['whats_working'],
                    'whats_holding_you_back': row['whats_holding_you_back'],
                    'how_others_experience_you': row['how_others_experience_you'],
                    'professional_impact': row['professional_impact'],
                    'highest_roi_improvement': row['highest_roi_improvement']
                }
                continue
        
        writeups[competency] = {
            'score': score,
            'score_range': score_range,
            'category': 'Not Available',
            'executive_narrative': 'No narrative available for this score range.',
            'whats_working': '',
            'whats_holding_you_back': '',
            'how_others_experience_you': '',
            'professional_impact': '',
            'highest_roi_improvement': ''
        }
    
    return writeups


# ============================================================
# DEEP COMMUNICATION ANALYSIS - AI ANALYST
# ============================================================

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
  
  "what_you_meant": "What the user likely intended to communicate (the core message they were trying to convey)",
  
  "what_you_said": "What the user actually said (the literal words and their surface meaning)",
  
  "what_landed": "What the listener likely heard and experienced (the perceived meaning, emotional impact, and takeaway)",
  
  "what_got_lost": "What the user intended that didn't get communicated effectively (nuance, subtext, credibility, emotion, etc.)",
  
  "the_unspoken_gap": "The gap between what was meant and what landed - why this gap exists and what it reveals",
  
  "why_it_matters": "Why this gap matters in the context of the conversation - the consequences and risks",
  
  "one_thing_to_change": "The single most impactful change the user should make in their communication",
  
  "behavioral_evidence": [
    "Specific behavioral observations from the response that support the analysis"
  ],
  
  "patterns_detected": [
    "Patterns in the user's communication style revealed by this response"
  ],
  
  "better_version": "A rewritten version of the response that bridges the unspoken gap and demonstrates the 'one thing to change'",
  
  "why_better": [
    "Explanation of why the better version works and how it bridges the gap"
  ]
}}

Return ONLY valid JSON. Do not include any other text or explanation."""

    return prompt


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
            print(f"⚠️ No JSON found in response")
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


def generate_mock_deep_analysis(text: str, scenario_id: int = 0):
    """Generate a mock deep analysis for fallback."""
    
    scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
    
    # Determine basic quality indicators
    word_count = len(text.split())
    has_numbers = bool(re.search(r'\d', text))
    has_clear_ask = bool(re.search(r'\?|please|recommend|suggest|propose|request', text, re.IGNORECASE))
    has_confidence = bool(re.search(r'I believe|I know|I\'m confident|I\'m sure|I think', text, re.IGNORECASE))
    has_impact = bool(re.search(r'deliver|achieve|result|outcome|success|goal', text, re.IGNORECASE))
    
    import random
    random.seed(hash(text) % 10000)
    
    scores = {
        'clarity': min(92, max(35, 45 + (20 if has_clear_ask else 0) + (8 if word_count > 15 else 0) + random.randint(-7, 7))),
        'precision': min(92, max(30, 40 + (25 if has_numbers else 0) + (8 if word_count > 20 else 0) + random.randint(-7, 7))),
        'structure': min(92, max(25, 35 + (30 if has_clear_ask else 0) + random.randint(-7, 7))),
        'impact': min(92, max(30, 40 + (20 if has_impact else 0) + (12 if has_clear_ask else 0) + random.randint(-7, 7))),
        'influence': min(92, max(25, 35 + (22 if has_confidence else 0) + (18 if has_clear_ask else 0) + random.randint(-7, 7)))
    }
    
    # Generate meaningful analysis based on scenario
    if scenario_id == 0:  # Deadline
        analysis = {
            "what_you_meant": "You wanted to explain the deadline situation and show you're taking responsibility",
            "what_you_said": "You mentioned the deadline issue but didn't provide enough context or a clear plan",
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
            "what_you_said": "You mentioned your experience but the message was scattered and unclear",
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
            "what_you_said": "The message was communicated but could be more impactful",
            "what_landed": "The listener may have missed the full meaning",
            "what_got_lost": "Some nuance and impact got lost in the delivery",
            "the_unspoken_gap": "Between your intention and the perceived message",
            "why_it_matters": "This affects how your message is received and acted upon",
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


def determine_emerging_persona(attempts_data: list):
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
    
    persona = PERSONA_MAP.get(strongest, PERSONA_MAP['clarity'])
    
    return {
        'persona': persona,
        'strongest': strongest.upper(),
        'weakest': weakest.upper()
    }


# ============================================================
# LEADS ENDPOINTS
# ============================================================

@app.post("/api/leads")
async def save_lead(lead: LeadCreate):
    conn = None
    try:
        if not lead.full_name or not lead.email:
            return {"success": False, "message": "full_name and email are required"}

        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        existing_lead = await conn.fetchrow(
            "SELECT full_name, email, phone, created_at FROM leads WHERE email = $1",
            lead.email
        )

        if existing_lead:
            await conn.close()
            return {"success": True, "message": "Lead already exists", "lead": dict(existing_lead)}

        await conn.execute(
            """
            INSERT INTO leads (full_name, email, phone, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            """,
            lead.full_name, lead.email, lead.phone
        )

        await conn.close()
        return {"success": True, "message": "Lead saved successfully"}

    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


@app.get("/api/leads")
async def get_all_leads():
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
            
        leads = await conn.fetch(
            "SELECT full_name, email, phone, created_at FROM leads ORDER BY created_at DESC"
        )
        await conn.close()
        return {"success": True, "leads": [dict(lead) for lead in leads], "count": len(leads)}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


@app.get("/api/leads/{email}")
async def get_lead_by_email(email: str):
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
            
        lead = await conn.fetchrow(
            "SELECT full_name, email, phone, created_at FROM leads WHERE email = $1",
            email
        )
        await conn.close()
        if not lead:
            return {"success": False, "message": "Lead not found"}
        return {"success": True, "lead": dict(lead)}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


# ============================================================
# PAID PERSONA ASSESSMENT ENDPOINT
# ============================================================

@app.post("/api/persona/paid-assess")
async def paid_persona_assessment(data: PersonaAssessmentRequest):
    conn = None
    try:
        print("=" * 50)
        print("📝 PAID PERSONA ASSESSMENT")
        print(f"Name  : {data.user_details.full_name}")
        print(f"Email : {data.user_details.email}")
        print(f"Phone : {data.user_details.phone}")
        print(f"Responses: {len(data.responses)}")
        print("=" * 50)

        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        user = await conn.fetchrow(
            "SELECT user_id FROM users WHERE email = $1",
            data.user_details.email
        )

        if not user:
            password = generate_password()
            password_hash = hash_password(password)
            
            user_id = await conn.fetchval(
                """
                INSERT INTO users (full_name, email, phone, password_hash, created_at, has_paid_persona)
                VALUES ($1, $2, $3, $4, NOW(), TRUE)
                RETURNING user_id
                """,
                data.user_details.full_name,
                data.user_details.email,
                data.user_details.phone,
                password_hash
            )
            print(f"✅ New user created: {user_id}")
            print(f"🔑 Password: {password}")
        else:
            user_id = user['user_id']
            await conn.execute(
                "UPDATE users SET has_paid_persona = TRUE WHERE user_id = $1",
                user_id
            )
            print(f"✅ Existing user updated: {user_id}")

        competency_scores = calculate_competency_scores(data.responses)
        persona_code = determine_persona_from_assessment(competency_scores)

        persona_content = await conn.fetchrow(
            "SELECT * FROM persona_content WHERE persona_code = $1",
            persona_code
        )
        if not persona_content:
            persona_content = await conn.fetchrow(
                "SELECT * FROM persona_content WHERE persona_code = 'ARTICULATOR'"
            )

        competency_writeups = await get_competency_writeups(conn, competency_scores)

        for r in data.responses:
            await conn.execute(
                """
                INSERT INTO paid_responses (user_id, question_code, answer, created_at)
                VALUES ($1, $2, $3, NOW())
                """,
                user_id,
                r.get('question_code'),
                r.get('answer')
            )

        await conn.execute(
            """
            INSERT INTO paid_personas (
                user_id, persona_code, persona_name, persona_description,
                strength, strength_description, blind_spot, tagline,
                structure_score, thinking_score, impact_score, 
                expression_score, connection_score, dimension_percentages
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            user_id,
            persona_content['persona_code'],
            persona_content['persona_name'],
            persona_content['description'],
            persona_content['strength'],
            persona_content['strength_description'],
            persona_content['blind_spot'],
            persona_content['tagline'],
            competency_scores['structure'],
            competency_scores['thinking'],
            competency_scores['impact'],
            competency_scores['expression'],
            competency_scores['connection'],
            json.dumps(competency_scores)
        )

        report = {
            "persona": {
                "code": persona_content['persona_code'],
                "name": persona_content['persona_name'],
                "description": persona_content['description'],
                "detailed_description": persona_content.get('detailed_description') or "",
                "strength": persona_content['strength'],
                "strength_description": persona_content['strength_description'],
                "natural_advantage": persona_content.get('natural_advantage') or "",
                "perception_to_watch": persona_content.get('perception_to_watch') or "",
                "strength_paradox": persona_content.get('strength_paradox') or "",
                "what_this_gives_you": persona_content.get('what_this_gives_you') or "",
                "what_this_costs_you": persona_content.get('what_this_costs_you') or "",
                "blind_spot": persona_content['blind_spot'],
                "blind_spot_description": persona_content.get('blind_spot_description') or "",
                "tagline": persona_content['tagline'],
                "communication_style": persona_content.get('communication_style') or "",
                "how_others_experience_you": persona_content.get('how_others_experience_you') or "",
                "growth_opportunities": persona_content.get('growth_opportunities') or "",
                "next_level": persona_content.get('next_level') or "",
                "your_highest_roi_move": persona_content.get('your_highest_roi_move') or ""
            },
            "competencies": competency_writeups,
            "scores": competency_scores
        }

        await conn.close()
        return {
            "success": True,
            "report": report,
            "user": {
                "user_id": str(user_id),
                "full_name": data.user_details.full_name,
                "email": data.user_details.email,
                "phone": data.user_details.phone
            }
        }

    except Exception as e:
        print(f"❌ Assessment error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


@app.get("/api/persona/paid-report/{user_id}")
async def get_paid_persona_report(user_id: str):
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        persona = await conn.fetchrow(
            """
            SELECT 
                persona_code,
                persona_name,
                persona_description,
                strength,
                strength_description,
                blind_spot,
                tagline,
                structure_score,
                thinking_score,
                impact_score,
                expression_score,
                connection_score,
                dimension_percentages,
                created_at
            FROM paid_personas
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id
        )

        if not persona:
            await conn.close()
            return {"success": False, "message": "No persona found for this user"}

        user = await conn.fetchrow(
            """
            SELECT full_name, email, phone
            FROM users
            WHERE user_id = $1
            """,
            user_id
        )

        try:
            content = await conn.fetchrow(
                """
                SELECT 
                    persona_code,
                    persona_name,
                    description,
                    detailed_description,
                    strength,
                    strength_description,
                    natural_advantage,
                    perception_to_watch,
                    strength_paradox,
                    what_this_gives_you,
                    what_this_costs_you,
                    blind_spot,
                    blind_spot_description,
                    tagline,
                    communication_style,
                    how_others_experience_you,
                    growth_opportunities,
                    next_level,
                    recommended_actions,
                    your_highest_roi_move
                FROM persona_content
                WHERE persona_code = $1
                """,
                persona['persona_code']
            )
        except Exception as e:
            print(f"⚠️ Error fetching persona content: {e}")
            content = None

        scores = persona['dimension_percentages']
        if isinstance(scores, str):
            scores = json.loads(scores)

        competency_writeups = await get_competency_writeups(conn, scores)

        if content:
            persona_data = {
                "user_name": user['full_name'] if user else "Professional",
                "user_email": user['email'] if user else "",
                "code": persona['persona_code'],
                "name": persona['persona_name'],
                "description": persona['persona_description'] or content.get('description', ''),
                "detailed_description": content.get('detailed_description', ''),
                "strength": persona['strength'] or content.get('strength', ''),
                "strength_description": persona['strength_description'] or content.get('strength_description', ''),
                "blind_spot": persona['blind_spot'] or content.get('blind_spot', ''),
                "blind_spot_description": content.get('blind_spot_description', ''),
                "tagline": persona['tagline'] or content.get('tagline', ''),
                "natural_advantage": content.get('natural_advantage', ''),
                "perception_to_watch": content.get('perception_to_watch', ''),
                "strength_paradox": content.get('strength_paradox', ''),
                "what_this_gives_you": content.get('what_this_gives_you', ''),
                "what_this_costs_you": content.get('what_this_costs_you', ''),
                "communication_style": content.get('communication_style', ''),
                "how_others_experience_you": content.get('how_others_experience_you', ''),
                "growth_opportunities": content.get('growth_opportunities', ''),
                "next_level": content.get('next_level', ''),
                "recommended_actions": content.get('recommended_actions', ''),
                "your_highest_roi_move": content.get('your_highest_roi_move', '')
            }
        else:
            persona_data = {
                "user_name": user['full_name'] if user else "Professional",
                "user_email": user['email'] if user else "",
                "code": persona['persona_code'],
                "name": persona['persona_name'],
                "description": persona['persona_description'] or "",
                "detailed_description": "",
                "strength": persona['strength'] or "",
                "strength_description": persona['strength_description'] or "",
                "blind_spot": persona['blind_spot'] or "",
                "blind_spot_description": "",
                "tagline": persona['tagline'] or "",
                "natural_advantage": "",
                "perception_to_watch": "",
                "strength_paradox": "",
                "what_this_gives_you": "",
                "what_this_costs_you": "",
                "communication_style": "",
                "how_others_experience_you": "",
                "growth_opportunities": "",
                "next_level": "",
                "recommended_actions": "",
                "your_highest_roi_move": ""
            }

        await conn.close()
        return {
            "success": True,
            "report": {
                "persona": persona_data,
                "competencies": competency_writeups,
                "scores": scores,
                "created_at": persona['created_at']
            }
        }

    except Exception as e:
        print(f"❌ Error fetching report: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}
    finally:
        if conn:
            await conn.close()


# ============================================================
# DEEP COMMUNICATION ANALYSIS ENDPOINT - THE UNSPOKEN ANALYST
# ============================================================

@app.post("/api/communication/analyze")
async def analyze_communication(request: CommunicationRequest):
    """
    Deep communication analysis using the Unspoken AI Analyst.
    Provides complete breakdown: what you meant, what you said, what landed, what got lost, etc.
    """
    try:
        print("=" * 60)
        print("🧠 THE UNSPOKEN AI ANALYST")
        print(f"Scenario: {request.scenario_id}")
        
        # --- EXTRACT ATTEMPTS ---
        attempts_data = []
        
        if request.attempts:
            attempts_data = request.attempts
            print(f"✅ Using attempts array: {len(attempts_data)} attempts")
        elif request.response:
            print("✅ Using single attempt format")
            attempts_data = [{
                'attempt': request.attempt or 1,
                'response': request.response,
                'mode': request.mode or 'text'
            }]
            
            if request.previous_attempts:
                for prev in request.previous_attempts:
                    attempts_data.insert(0, {
                        'attempt': prev.get('attempt', 1),
                        'response': prev.get('response', ''),
                        'mode': prev.get('mode', 'text')
                    })
                print(f"✅ Added {len(request.previous_attempts)} previous attempts")
        else:
            return {"success": False, "message": "No attempt data provided"}
        
        # ENFORCE 3 ATTEMPTS LIMIT
        if len(attempts_data) > 3:
            return {
                "success": False, 
                "message": "Maximum 3 attempts allowed per scenario."
            }
        
        print(f"Total attempts: {len(attempts_data)}")
        print("=" * 60)

        scenario = SCENARIOS[request.scenario_id] if request.scenario_id < len(SCENARIOS) else SCENARIOS[0]
        
# Process each attempt with deep analysis
results = []
previous_responses = []

for attempt in attempts_data:
    # Handle both dict and AttemptData objects
    if hasattr(attempt, 'attempt'):
        attempt_num = attempt.attempt
        response_text = attempt.response
        mode = attempt.mode
    else:
        attempt_num = attempt.get('attempt', 1)
        response_text = attempt.get('response', '')
        mode = attempt.get('mode', 'text')
    
    print(f"\n📝 Analyzing Attempt {attempt_num}...")
    print(f"   Response: {response_text[:100]}...")
    
    # Build deep analysis prompt
    prompt = build_deep_analysis_prompt(
        request.scenario_id,
        response_text,
        attempt_num,
        len(attempts_data),
        previous_responses
    )
    
    # Call Gemini for deep analysis
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
        mock = generate_mock_deep_analysis(response_text, request.scenario_id)
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
            
            # Build deep analysis prompt
            prompt = build_deep_analysis_prompt(
                request.scenario_id,
                attempt['response'],
                attempt['attempt'],
                len(attempts_data),
                previous_responses
            )
            
            # Call Gemini for deep analysis
            gemini_result = call_gemini_api(prompt)
            
            if gemini_result and 'scores' in gemini_result:
                print("✅ Using Gemini deep analysis")
                result = {
                    'attempt': attempt['attempt'],
                    'mode': attempt['mode'],
                    'response': attempt['response'],
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
                mock = generate_mock_deep_analysis(attempt['response'], request.scenario_id)
                result = {
                    'attempt': attempt['attempt'],
                    'mode': attempt['mode'],
                    'response': attempt['response'],
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
                'attempt': attempt['attempt'],
                'response': attempt['response']
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
                'id': request.scenario_id,
                'context': scenario['context'],
                'question': scenario['question']
            },
            'attempts_remaining': max(0, 3 - len(results)),
            'message': f'Analysis complete for attempt {len(results)} of 3'
        }
        
        # If 3 attempts complete, determine emerging persona
        if is_complete:
            persona_result = determine_emerging_persona(results)
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


@app.get("/api/communication/scenarios")
async def get_communication_scenarios():
    """Get all scenarios."""
    return {"success": True, "scenarios": SCENARIOS}


@app.get("/api/test-gemini")
async def test_gemini():
    """Test if Gemini API is working."""
    config_status = {
        "gemini_key_set": bool(GEMINI_API_KEY),
        "gemini_key_value": GEMINI_API_KEY[:10] + "..." if GEMINI_API_KEY else "None",
        "model_initialized": bool(model) if 'model' in globals() else False,
        "api_key_length": len(GEMINI_API_KEY) if GEMINI_API_KEY else 0
    }
    
    if not GEMINI_API_KEY:
        return {
            "success": False,
            "message": "GEMINI_API_KEY not set in environment variables",
            "config": config_status
        }
    
    if not model:
        return {
            "success": False,
            "message": "Gemini model not initialized",
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
            "error_type": type(e).__name__,
            "config": config_status
        }


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY and GEMINI_API_KEY != ""),
        "database_configured": bool(os.environ.get("DATABASE_URL")),
        "service": "Unspoken Backend",
        "cors_configured": True
    }


@app.get("/")
async def root():
    return {
        "service": "Unspoken Backend",
        "status": "running",
        "endpoints": [
            "POST /api/leads - Save a new lead",
            "GET /api/leads - Get all leads",
            "POST /api/persona/paid-assess - Paid Persona Assessment",
            "GET /api/persona/paid-report/{user_id} - Get Paid Persona Report",
            "POST /api/communication/analyze - Deep Communication Analysis (The Unspoken Analyst)",
            "GET /api/communication/scenarios - Get all scenarios",
            "GET /api/test-gemini - Test Gemini API connection",
            "GET /api/health - Health check"
        ]
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
