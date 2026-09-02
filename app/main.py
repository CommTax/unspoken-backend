from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(
    title="Unspoken Backend",
    description="Paid Persona Assessment + Communication Analysis",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# MODELS - UPDATED TO HANDLE BOTH PAYLOAD FORMATS
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
    mode: str  # 'voice' or 'text'


class AnalysisDimension(BaseModel):
    name: str
    description: str


class FeedbackStyle(BaseModel):
    tone: str
    format: str
    priority: str


class CoachingInstructions(BaseModel):
    analysis_dimensions: Optional[List[AnalysisDimension]] = None
    feedback_style: Optional[FeedbackStyle] = None
    better_version_instructions: Optional[List[str]] = None
    why_it_works_instructions: Optional[List[str]] = None
    user_context: Optional[Dict[str, Any]] = None


class CommunicationRequest(BaseModel):
    # Core fields - scenario_id is required
    scenario_id: int
    
    # For new format with attempts array
    attempts: Optional[List[AttemptData]] = None
    
    # For backward compatibility with old format
    scenario_context: Optional[str] = None
    scenario_question: Optional[str] = None
    response: Optional[str] = None
    attempt: Optional[int] = None
    mode: Optional[str] = None
    previous_attempts: Optional[List[Dict[str, Any]]] = None
    
    # Coaching instructions (optional)
    coaching_instructions: Optional[CoachingInstructions] = None


# ============================================================
# SCENARIOS DATA
# ============================================================

SCENARIOS = [
    {
        "id": 0,
        "context": "Your team missed a key deadline. You need to update your manager.",
        "question": "Your manager asks: 'What happened with the deadline, and what's your plan to fix it?'",
        "better": "We're behind on the project timeline due to unexpected technical dependencies. I've identified the bottlenecks and created a recovery plan. We can deliver by Friday if we reprioritize the backlog. I'll share the detailed plan after this meeting. Does that approach work for you?"
    },
    {
        "id": 1,
        "context": "A client says your proposal is too expensive. You need to respond and keep the deal alive.",
        "question": "The client says: 'Your price is 30% higher than your competitor's. Why should we go with you?'",
        "better": "I understand budget is a concern. Let me walk you through the ROI — this solution saves you 30% on operational costs within the first year. I can also offer a phased deployment to spread the cost. Would a 6-month payment plan work for your team?"
    },
    {
        "id": 2,
        "context": "You want to ask your manager for a promotion. Draft your pitch.",
        "question": "Your manager says: 'Tell me why you deserve a promotion right now.'",
        "better": "I'd like to discuss advancing to the next level. Over the past year, I've exceeded my targets by 20%, led two successful product launches, and taken on mentorship responsibilities. I believe I'm ready to take on more strategic ownership. Can we schedule time next week to discuss this?"
    },
    {
        "id": 3,
        "context": "You need to give constructive feedback to a teammate who's been underperforming.",
        "question": "Your teammate asks: 'Is there anything I could be doing better?'",
        "better": "I want to discuss your recent deliverables. I've noticed a few inconsistencies in quality and missed deadlines. I know you're capable of great work — what support do you need from me to get back on track? Let's work together to improve this."
    },
    {
        "id": 4,
        "context": "You're in a job interview. The interviewer asks the classic opening question.",
        "question": "Interviewer: 'Tell me about yourself.'",
        "better": "I'm a product manager with 5 years of experience in fintech. I led the launch of a mobile banking app that grew to 200K users in 6 months. I specialize in bridging the gap between business goals and technical execution. I'm looking to bring that expertise to a scaling startup like yours."
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
    """
    Calculate scores for 5 competencies from 30 questions.
    """
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
        
        # Fallback if no DB or no row found
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
# COMMUNICATION ANALYSIS - GEMINI FUNCTIONS
# ============================================================

def build_full_analysis_prompt(scenario_id: int, response_text: str, attempt: int, total_attempts: int, previous_scores: list = None, coaching_instructions: CoachingInstructions = None):
    """Build the enhanced prompt for Gemini API with all required fields."""
    
    scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
    
    prompt = f"""
You are a world-class communication coach. Analyze the user's response to this scenario:

SCENARIO CONTEXT: {scenario['context']}
QUESTION: {scenario['question']}

USER'S RESPONSE: {response_text}

This is attempt {attempt} of {total_attempts}.
"""

    if previous_scores and len(previous_scores) > 0:
        prompt += f"\nPREVIOUS ATTEMPTS SCORES: {json.dumps(previous_scores)}"
        prompt += "\nCompare this attempt to the previous ones. Note improvement or decline."

    # Add coaching instructions if provided
    if coaching_instructions:
        prompt += "\n\nCOACHING INSTRUCTIONS:"
        
        if coaching_instructions.analysis_dimensions:
            prompt += "\n\nAnalyze these dimensions:"
            for dim in coaching_instructions.analysis_dimensions:
                prompt += f"\n- {dim.name.upper()}: {dim.description}"
        
        if coaching_instructions.feedback_style:
            prompt += f"\n\nFEEDBACK STYLE:"
            prompt += f"\n- Tone: {coaching_instructions.feedback_style.tone}"
            prompt += f"\n- Format: {coaching_instructions.feedback_style.format}"
            prompt += f"\n- Priority: {coaching_instructions.feedback_style.priority}"
        
        if coaching_instructions.better_version_instructions:
            prompt += "\n\nBETTER VERSION INSTRUCTIONS:"
            for instruction in coaching_instructions.better_version_instructions:
                prompt += f"\n- {instruction}"
        
        if coaching_instructions.why_it_works_instructions:
            prompt += "\n\nWHY IT WORKS INSTRUCTIONS:"
            for instruction in coaching_instructions.why_it_works_instructions:
                prompt += f"\n- {instruction}"

    prompt += """

Now provide your analysis in this exact JSON format:

{
  "scores": {
    "clarity": 75,
    "precision": 70,
    "structure": 65,
    "impact": 80,
    "influence": 68
  },
  "feedback": [
    "⚠️ Unclear — Your main point isn't obvious. State your core message upfront.",
    "⚠️ Vague — Use specific numbers, dates, or concrete examples.",
    "⚠️ Scattered — Try: Context → Problem → Solution → Ask.",
    "⚠️ Forgettable — What's the one thing you want them to remember?",
    "⚠️ Uncompelling — Add a clear call to action."
  ],
  "betterVersion": "Here is an improved version of your response...",
  "whyItWorks": [
    "Clarity: States the main point immediately",
    "Structure: Follows a logical flow: Context → Action → Ask",
    "Influence: Ends with a clear, actionable question",
    "Precision: Uses specific, concrete language"
  ]
}

RETURN ONLY VALID JSON. Do not include any other text or explanation.
"""
    return prompt


def call_gemini_api(prompt: str):
    """Call Gemini API with the prompt."""
    try:
        if not GEMINI_API_KEY or not model:
            return None
            
        response = model.generate_content(prompt)
        
        # Extract JSON from response
        text = response.text
        
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            print(f"⚠️ No JSON found in response: {text[:200]}...")
            return None
            
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return None


def generate_enhanced_mock_result(text: str, scenario_id: int = 0):
    """Enhanced fallback mock analysis with all fields."""
    word_count = len(text.split())
    has_structure = bool(re.search(r'first|second|finally|next|then|firstly|secondly', text, re.IGNORECASE))
    has_clear_ask = bool(re.search(r'\?|please|recommend|suggest|propose|request', text, re.IGNORECASE))
    has_numbers = bool(re.search(r'\d', text))
    has_confidence = bool(re.search(r'I believe|I know|I\'m confident|I\'m sure|I think', text, re.IGNORECASE))
    has_impact = bool(re.search(r'deliver|achieve|result|outcome|success|goal', text, re.IGNORECASE))

    import random
    random.seed(hash(text) % 10000)
    
    scores = {
        'clarity': min(92, max(35, 55 + (20 if has_clear_ask else 0) + (8 if word_count > 15 else 0) + random.randint(-7, 7))),
        'precision': min(92, max(30, 45 + (25 if has_numbers else 0) + (8 if word_count > 20 else 0) + random.randint(-7, 7))),
        'structure': min(92, max(25, 35 + (30 if has_structure else 0) + (8 if word_count > 20 else 0) + random.randint(-7, 7))),
        'impact': min(92, max(30, 45 + (20 if has_impact else 0) + (12 if has_clear_ask else 0) + random.randint(-7, 7))),
        'influence': min(92, max(25, 35 + (22 if has_confidence else 0) + (18 if has_clear_ask else 0) + random.randint(-7, 7)))
    }
    
    # Generate feedback based on scores
    feedback = []
    if scores['clarity'] < 65:
        feedback.append("⚠️ Unclear — Your main point isn't obvious. State your core message upfront.")
    elif scores['clarity'] < 80:
        feedback.append("🟡 Moderately Clear — Your point is there, but could be sharper.")
    else:
        feedback.append("✅ Clear — Your main point comes through effectively.")
    
    if scores['precision'] < 65:
        feedback.append("⚠️ Vague — Use specific numbers, dates, or concrete examples.")
    elif scores['precision'] < 80:
        feedback.append("🟡 Somewhat Precise — Add more specific details.")
    else:
        feedback.append("✅ Precise — Good use of specific details.")
    
    if scores['structure'] < 65:
        feedback.append("⚠️ Scattered — Try: Context → Problem → Solution → Ask.")
    elif scores['structure'] < 80:
        feedback.append("🟡 Partly Structured — Could be more organized.")
    else:
        feedback.append("✅ Structured — Clear logical flow.")
    
    if scores['impact'] < 65:
        feedback.append("⚠️ Forgettable — What's the one thing you want them to remember?")
    elif scores['impact'] < 80:
        feedback.append("🟡 Moderate Impact — End with a strong closing statement.")
    else:
        feedback.append("✅ Impactful — Memorable and leaves a strong impression.")
    
    if scores['influence'] < 65:
        feedback.append("⚠️ Uncompelling — Add a clear call to action.")
    elif scores['influence'] < 80:
        feedback.append("🟡 Somewhat Compelling — Strengthen your ask.")
    else:
        feedback.append("✅ Influential — Compelling case with clear action.")
    
    # Get better version from scenarios
    scenario = SCENARIOS[scenario_id] if scenario_id < len(SCENARIOS) else SCENARIOS[0]
    better_version = scenario['better']
    
    # Generate "Why it works" based on the better version
    why_it_works = [
        "Clarity: States the main point immediately",
        "Structure: Follows a logical flow: Context → Action → Ask",
        "Influence: Ends with a clear, actionable question",
        "Precision: Uses specific, concrete language"
    ]
    
    return {
        'scores': scores,
        'feedback': feedback,
        'betterVersion': better_version,
        'whyItWorks': why_it_works
    }


def determine_persona_from_attempts(attempts_data: list):
    """Determine persona based on all attempts."""
    dims = ['clarity', 'precision', 'structure', 'impact', 'influence']
    totals = {d: 0 for d in dims}
    
    for attempt in attempts_data:
        scores = attempt.get('scores', {})
        for d in dims:
            totals[d] += scores.get(d, 50)
    
    # Find strongest
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

        # --- 1. Create or Get User ---
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

        # --- 2. Calculate Scores ---
        competency_scores = calculate_competency_scores(data.responses)
        persona_code = determine_persona_from_assessment(competency_scores)

        # --- 3. Get Persona Content ---
        persona_content = await conn.fetchrow(
            "SELECT * FROM persona_content WHERE persona_code = $1",
            persona_code
        )
        if not persona_content:
            persona_content = await conn.fetchrow(
                "SELECT * FROM persona_content WHERE persona_code = 'ARTICULATOR'"
            )

        # --- 4. Get Competency Write-ups ---
        competency_writeups = await get_competency_writeups(conn, competency_scores)

        # --- 5. Store Responses ---
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

        # --- 6. Store Persona Result ---
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

        # --- 7. Build Report ---
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


# ============================================================
# GET PAID PERSONA REPORT
# ============================================================

@app.get("/api/persona/paid-report/{user_id}")
async def get_paid_persona_report(user_id: str):
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        # Get the persona result from paid_personas
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

        # Get user details
        user = await conn.fetchrow(
            """
            SELECT full_name, email, phone
            FROM users
            WHERE user_id = $1
            """,
            user_id
        )

        # Get persona content
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

        # Get competency write-ups
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
# COMMUNICATION ANALYSIS ENDPOINT - UPDATED
# ============================================================

@app.post("/api/communication/analyze")
async def analyze_communication(request: CommunicationRequest):
    """
    Analyze communication attempts using Gemini AI.
    Handles both enhanced payload with coaching instructions and simple payload.
    Returns scores, feedback, better version, and why it works.
    """
    try:
        print("=" * 50)
        print("📝 COMMUNICATION ANALYSIS")
        print(f"Scenario: {request.scenario_id}")
        
        # --- EXTRACT ATTEMPTS FROM PAYLOAD ---
        attempts_data = []
        
        if request.attempts:
            # New format: attempts array provided
            attempts_data = request.attempts
            print(f"✅ Using attempts array format: {len(attempts_data)} attempts")
        elif request.response:
            # Old/Backward compatible format: single attempt with response
            print("✅ Using single attempt format")
            attempts_data = [AttemptData(
                attempt=request.attempt or 1,
                response=request.response,
                mode=request.mode or 'text'
            )]
            
            # Include previous attempts if provided
            if request.previous_attempts:
                for prev in request.previous_attempts:
                    attempts_data.insert(0, AttemptData(
                        attempt=prev.get('attempt', 1),
                        response=prev.get('response', ''),
                        mode=prev.get('mode', 'text')
                    ))
                print(f"✅ Added {len(request.previous_attempts)} previous attempts")
        else:
            return {"success": False, "message": "No attempt data provided"}
        
        # ENFORCE 3 ATTEMPTS LIMIT
        if len(attempts_data) > 3:
            return {
                "success": False, 
                "message": "Maximum 3 attempts allowed per scenario. Please start a new scenario."
            }
        
        print(f"Total attempts: {len(attempts_data)}")
        if request.coaching_instructions:
            print("✅ Coaching instructions provided")
        print("=" * 50)

        scenario = SCENARIOS[request.scenario_id] if request.scenario_id < len(SCENARIOS) else SCENARIOS[0]
        
        # Process each attempt
        results = []
        previous_scores = []
        
        for attempt in attempts_data:
            # Build enhanced prompt for Gemini with coaching instructions
            prompt = build_full_analysis_prompt(
                request.scenario_id,
                attempt.response,
                attempt.attempt,
                len(attempts_data),
                previous_scores,
                request.coaching_instructions  # Pass coaching instructions to prompt
            )
            
            # Call Gemini
            gemini_result = call_gemini_api(prompt)
            
            if gemini_result and 'scores' in gemini_result:
                # Use Gemini result with all fields
                result = {
                    'attempt': attempt.attempt,
                    'mode': attempt.mode,
                    'response': attempt.response,
                    'scores': gemini_result['scores'],
                    'feedback': gemini_result.get('feedback', []),
                    'betterVersion': gemini_result.get('betterVersion', scenario['better']),
                    'whyItWorks': gemini_result.get('whyItWorks', [])
                }
            else:
                # Fallback to enhanced mock
                mock = generate_enhanced_mock_result(attempt.response, request.scenario_id)
                result = {
                    'attempt': attempt.attempt,
                    'mode': attempt.mode,
                    'response': attempt.response,
                    'scores': mock['scores'],
                    'feedback': mock['feedback'],
                    'betterVersion': mock['betterVersion'],
                    'whyItWorks': mock['whyItWorks']
                }
            
            results.append(result)
            previous_scores.append(result['scores'])
        
        # Calculate overall scores
        dims = ['clarity', 'precision', 'structure', 'impact', 'influence']
        overall_scores = {d: 0 for d in dims}
        for result in results:
            for d in dims:
                overall_scores[d] += result['scores'][d]
        
        for d in dims:
            overall_scores[d] = round(overall_scores[d] / len(results), 2)
        
        # Find best attempt
        best_attempt = max(results, key=lambda x: sum(x['scores'].values()) / 5)
        
        # Determine if all 3 attempts are complete
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
            'attempts_remaining': max(0, 3 - len(results))
        }
        
        # If 3 attempts complete, calculate persona
        if is_complete:
            persona_result = determine_persona_from_attempts(results)
            response_data['persona'] = {
                'name': persona_result['persona']['name'],
                'description': persona_result['persona']['description'],
                'strength_label': persona_result['persona']['strength_label'],
                'strength_desc': persona_result['persona']['strength_desc'],
                'growth_label': persona_result['persona']['growth_label'],
                'growth_desc': persona_result['persona']['growth_desc'],
                'strongest_dimension': persona_result['strongest'],
                'weakest_dimension': persona_result['weakest']
            }
            response_data['message'] = 'All 3 attempts analyzed. Persona revealed!'
        else:
            response_data['message'] = f'Analysis complete for attempt {len(results)} of 3'
        
        print(f"✅ Analysis complete. Complete: {is_complete}")
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


# ============================================================
# ROOT & HEALTH
# ============================================================

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
            "POST /api/communication/analyze - Analyze communication attempts (max 3)",
            "GET /api/communication/scenarios - Get all scenarios"
        ]
    }


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "gemini_configured": bool(GEMINI_API_KEY and GEMINI_API_KEY != ""),
        "database_configured": bool(os.environ.get("DATABASE_URL")),
        "service": "Unspoken Backend"
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
