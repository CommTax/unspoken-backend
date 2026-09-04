import asyncpg
import json
import os
from app.utils.helpers import get_db, hash_password, generate_password
from app.utils.scenarios import PERSONA_MAP

async def process_persona_assessment(data):
    """Process the full persona assessment with scoring."""
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        # Create or get user
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

        # Calculate scores
        competency_scores = calculate_competency_scores(data.responses)
        persona_code = determine_persona(competency_scores)

        # Get persona content
        persona_content = await conn.fetchrow(
            "SELECT * FROM persona_content WHERE persona_code = $1",
            persona_code
        )
        if not persona_content:
            persona_content = await conn.fetchrow(
                "SELECT * FROM persona_content WHERE persona_code = 'ARTICULATOR'"
            )

        # Get competency write-ups
        competency_writeups = await get_competency_writeups(conn, competency_scores)

        # Store responses
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

        # Store persona result
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

        # Build report
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

async def get_persona_report(user_id: str):
    """Get a persona report for a user."""
    conn = None
    try:
        conn = await get_db()
        if not conn:
            return {"success": False, "message": "Database connection failed"}

        # Get persona
        persona = await conn.fetchrow(
            """
            SELECT 
                persona_code, persona_name, persona_description,
                strength, strength_description, blind_spot, tagline,
                structure_score, thinking_score, impact_score, 
                expression_score, connection_score, dimension_percentages,
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
            return {"success": False, "message": "No persona found"}

        # Get user
        user = await conn.fetchrow(
            "SELECT full_name, email, phone FROM users WHERE user_id = $1",
            user_id
        )

        # Get persona content
        content = await conn.fetchrow(
            "SELECT * FROM persona_content WHERE persona_code = $1",
            persona['persona_code']
        )

        scores = persona['dimension_percentages']
        if isinstance(scores, str):
            scores = json.loads(scores)

        competency_writeups = await get_competency_writeups(conn, scores)

        persona_data = {
            "user_name": user['full_name'] if user else "Professional",
            "user_email": user['email'] if user else "",
            "code": persona['persona_code'],
            "name": persona['persona_name'],
            "description": persona['persona_description'] or (content.get('description') if content else ''),
            "strength": persona['strength'] or (content.get('strength') if content else ''),
            "strength_description": persona['strength_description'] or (content.get('strength_description') if content else ''),
            "blind_spot": persona['blind_spot'] or (content.get('blind_spot') if content else ''),
            "tagline": persona['tagline'] or (content.get('tagline') if content else ''),
            "detailed_description": content.get('detailed_description') if content else '',
            "natural_advantage": content.get('natural_advantage') if content else '',
            "perception_to_watch": content.get('perception_to_watch') if content else '',
            "strength_paradox": content.get('strength_paradox') if content else '',
            "what_this_gives_you": content.get('what_this_gives_you') if content else '',
            "what_this_costs_you": content.get('what_this_costs_you') if content else '',
            "blind_spot_description": content.get('blind_spot_description') if content else '',
            "communication_style": content.get('communication_style') if content else '',
            "how_others_experience_you": content.get('how_others_experience_you') if content else '',
            "growth_opportunities": content.get('growth_opportunities') if content else '',
            "next_level": content.get('next_level') if content else '',
            "recommended_actions": content.get('recommended_actions') if content else '',
            "your_highest_roi_move": content.get('your_highest_roi_move') if content else ''
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
# HELPER FUNCTIONS FOR PERSONA ASSESSMENT
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

def determine_persona(competency_scores):
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
                    competency, score_range, category,
                    executive_narrative, whats_working,
                    whats_holding_you_back, how_others_experience_you,
                    professional_impact, highest_roi_improvement
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
            'executive_narrative': 'No narrative available.',
            'whats_working': '',
            'whats_holding_you_back': '',
            'how_others_experience_you': '',
            'professional_impact': '',
            'highest_roi_improvement': ''
        }
    
    return writeups

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
