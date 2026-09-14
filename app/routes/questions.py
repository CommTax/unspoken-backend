# app/routes/questions.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import asyncpg

from app.config import Config

router = APIRouter()


# ============================================================
# GET /api/questions — fetch question bank by sprint + day
# ============================================================
@router.get("")
async def get_questions(
    sprint: str = Query(..., description="Sprint type: interview, gd, leadership, storytelling, charisma"),
    day: Optional[int] = Query(None, description="Optional: only return questions for this day"),
    limit: int = Query(50, le=200),
):
    """
    Returns questions from the question_bank table.
    - If `day` is provided, returns only questions for that day.
    - Otherwise returns all questions for the sprint (up to `limit`).
    """
    if sprint not in ("interview", "gd", "leadership", "storytelling", "charisma"):
        raise HTTPException(status_code=400, detail="Invalid sprint type")

    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        if day is not None:
            rows = await conn.fetch(
                """
                SELECT id, sprint, text, focus, target_seconds, difficulty, day_number
                FROM question_bank
                WHERE sprint = $1 AND day_number = $2
                ORDER BY id ASC
                """,
                sprint, day,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, sprint, text, focus, target_seconds, difficulty, day_number
                FROM question_bank
                WHERE sprint = $1
                ORDER BY day_number ASC, id ASC
                LIMIT $2
                """,
                sprint, limit,
            )

        return {
            "sprint": sprint,
            "day": day,
            "count": len(rows),
            "questions": [dict(r) for r in rows],
        }
    finally:
        await conn.close()


# ============================================================
# POST /api/questions/seed — one-time bulk insert (run once)
# ============================================================
@router.post("/seed")
async def seed_questions():
    """
    Seeds the question_bank table with default questions.
    Call once via Postman or curl.
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        # Check if already seeded
        existing = await conn.fetchval("SELECT COUNT(*) FROM question_bank")
        if existing > 0:
            return {"status": "already_seeded", "count": existing}

        seed_data = [
            # INTERVIEW SPRINT (Day 1-14, 2 per day = 28 questions)
            ("interview", "Tell me about yourself.", "Structure & Conciseness", 60, "Easy", 1),
            ("interview", "Walk me through your resume.", "Narrative & Relevance", 90, "Medium", 1),
            ("interview", "Why do you want to work here?", "Motivation & Fit", 60, "Easy", 2),
            ("interview", "Tell me about a time you faced a challenge at work.", "STAR Method", 90, "Medium", 2),
            ("interview", "What is your greatest strength?", "Self-Awareness", 45, "Easy", 3),
            ("interview", "What is your biggest weakness?", "Honesty & Growth", 60, "Hard", 3),
            ("interview", "Where do you see yourself in 5 years?", "Vision & Fit", 60, "Medium", 4),
            ("interview", "Why are you leaving your current role?", "Professional Narrative", 60, "Hard", 4),
            ("interview", "Describe a project you're most proud of.", "Impact & Ownership", 90, "Medium", 5),
            ("interview", "Tell me about a time you failed.", "Resilience & Learning", 90, "Hard", 5),
            ("interview", "How do you handle conflict with a colleague?", "Interpersonal Skills", 60, "Medium", 6),
            ("interview", "What motivates you day to day?", "Values & Drive", 60, "Easy", 6),
            ("interview", "Tell me about a time you led a team.", "Leadership", 90, "Medium", 7),
            ("interview", "How do you prioritize when everything is urgent?", "Time Management", 60, "Medium", 7),
            ("interview", "What's a skill you're currently developing?", "Growth Mindset", 45, "Easy", 8),
            ("interview", "Tell me about a time you disagreed with your manager.", "Diplomacy", 90, "Hard", 8),
            ("interview", "How do you approach a problem you've never seen before?", "Problem Solving", 60, "Medium", 9),
            ("interview", "What do you know about our company?", "Research & Interest", 60, "Easy", 9),
            ("interview", "Describe a time you had to influence without authority.", "Influence", 90, "Hard", 10),
            ("interview", "How do you handle feedback?", "Coachability", 45, "Easy", 10),
            ("interview", "Tell me about your biggest achievement.", "Impact", 90, "Medium", 11),
            ("interview", "What's a decision you regret?", "Reflection", 90, "Hard", 11),
            ("interview", "How do you stay current in your field?", "Continuous Learning", 60, "Easy", 12),
            ("interview", "Tell me about a time you had to say no.", "Boundaries & Prioritization", 60, "Medium", 12),
            ("interview", "Why should we hire you?", "Self-Advocacy", 60, "Medium", 13),
            ("interview", "What questions do you have for us?", "Curiosity & Engagement", 60, "Easy", 13),
            ("interview", "Describe your ideal work environment.", "Culture Fit", 60, "Medium", 14),
            ("interview", "Tell me about a time you went above and beyond.", "Initiative", 90, "Medium", 14),

            # GD SPRINT (7 days, 2/day = 14 questions)
            ("gd", "Is remote work here to stay?", "Opening Statement", 45, "Easy", 1),
            ("gd", "Should AI replace human decision-making?", "Balanced Argument", 60, "Medium", 1),
            ("gd", "Is hustle culture toxic?", "Perspective & Reasoning", 60, "Medium", 2),
            ("gd", "Does social media do more harm than good?", "Structured Argument", 60, "Easy", 2),
            ("gd", "Should college education be free?", "Pros & Cons", 60, "Medium", 3),
            ("gd", "Is work-from-home more productive than office?", "Evidence-Based Argument", 60, "Medium", 3),
            ("gd", "Should companies adopt 4-day work weeks?", "Nuanced Argument", 60, "Medium", 4),
            ("gd", "Is entrepreneurship better than a stable job?", "Personal Values", 60, "Medium", 4),
            ("gd", "Should CEOs be paid 100x their employees?", "Economic Reasoning", 60, "Hard", 5),
            ("gd", "Is privacy dead in the digital age?", "Ethical Reasoning", 60, "Hard", 5),
            ("gd", "Should India adopt a two-party system?", "Political Argument", 60, "Hard", 6),
            ("gd", "Is MBA still worth it in 2025?", "Cost-Benefit Analysis", 60, "Medium", 6),
            ("gd", "Should we ban targeted advertising?", "Ethics & Trade-offs", 60, "Medium", 7),
            ("gd", "Will AI create more jobs than it destroys?", "Long-term View", 60, "Hard", 7),

            # LEADERSHIP SPRINT (7 days, 2/day = 14 questions)
            ("leadership", "How do you motivate an underperforming team member?", "Empathy & Action", 90, "Medium", 1),
            ("leadership", "Describe a time you had to make a tough decision.", "Decision-Making", 90, "Medium", 1),
            ("leadership", "How do you handle conflict between two team members?", "Mediation", 60, "Hard", 2),
            ("leadership", "How do you give constructive feedback?", "Communication", 60, "Medium", 2),
            ("leadership", "How do you build trust with a new team?", "Trust Building", 90, "Medium", 3),
            ("leadership", "Describe your leadership style.", "Self-Awareness", 60, "Easy", 3),
            ("leadership", "How do you handle a team member who consistently underperforms?", "Accountability", 90, "Hard", 4),
            ("leadership", "How do you align a team around a vision?", "Vision Communication", 90, "Medium", 4),
            ("leadership", "Tell me about a time you had to let someone go.", "Difficult Conversations", 90, "Hard", 5),
            ("leadership", "How do you prioritize what your team works on?", "Strategic Prioritization", 60, "Medium", 5),
            ("leadership", "How do you handle disagreement with your boss?", "Managing Up", 60, "Medium", 6),
            ("leadership", "How do you develop your team members?", "Coaching & Growth", 60, "Medium", 6),
            ("leadership", "How do you handle change resistance?", "Change Management", 90, "Hard", 7),
            ("leadership", "What's the hardest leadership decision you've made?", "Judgment", 90, "Hard", 7),

            # STORYTELLING SPRINT (7 days, 2/day = 14 questions)
            ("storytelling", "Tell me about a defining moment in your career.", "Narrative Arc", 90, "Medium", 1),
            ("storytelling", "Describe a failure that shaped you.", "Vulnerability & Insight", 90, "Hard", 1),
            ("storytelling", "What is the story behind your biggest achievement?", "Emotional Hooks", 90, "Medium", 2),
            ("storytelling", "Tell me about a person who changed your life.", "Character & Impact", 90, "Medium", 2),
            ("storytelling", "Describe a moment you felt truly alive.", "Sensory Detail", 90, "Medium", 3),
            ("storytelling", "What's a lesson you learned the hard way?", "Reflection", 90, "Medium", 3),
            ("storytelling", "Tell me about a time you surprised yourself.", "Self-Discovery", 90, "Medium", 4),
            ("storytelling", "Describe a place that shaped who you are.", "Setting & Meaning", 90, "Easy", 4),
            ("storytelling", "What's a belief you've changed your mind about?", "Intellectual Honesty", 90, "Hard", 5),
            ("storytelling", "Tell me about a risk that paid off.", "Courage & Outcome", 90, "Medium", 5),
            ("storytelling", "Describe a moment of unexpected kindness.", "Emotion & Empathy", 90, "Easy", 6),
            ("storytelling", "Tell me about a time you felt like an outsider.", "Belonging", 90, "Hard", 6),
            ("storytelling", "What's a story you tell about yourself often?", "Identity", 90, "Medium", 7),
            ("storytelling", "Tell me about a loss that changed you.", "Grief & Growth", 90, "Hard", 7),

            # CHARISMA SPRINT (7 days, 2/day = 14 questions)
            ("charisma", "How would you introduce yourself in 30 seconds at a networking event?", "Presence", 30, "Easy", 1),
            ("charisma", "How do you make someone feel heard in a conversation?", "Connection", 60, "Medium", 1),
            ("charisma", "How do you command a room without dominating it?", "Executive Presence", 60, "Hard", 2),
            ("charisma", "What makes someone instantly likable?", "Social Intelligence", 60, "Medium", 2),
            ("charisma", "How do you handle an awkward silence?", "Composure", 30, "Easy", 3),
            ("charisma", "How do you remember names and details about people?", "Attention", 45, "Medium", 3),
            ("charisma", "How do you end a conversation gracefully?", "Social Grace", 30, "Easy", 4),
            ("charisma", "How do you disagree without being disagreeable?", "Tact", 60, "Hard", 4),
            ("charisma", "How do you show confidence without arrogance?", "Humility & Presence", 60, "Hard", 5),
            ("charisma", "How do you give a compliment that lands?", "Sincerity", 30, "Easy", 5),
            ("charisma", "How do you handle someone who talks over you?", "Assertiveness", 60, "Medium", 6),
            ("charisma", "How do you build rapport in 5 minutes?", "Speed & Warmth", 60, "Medium", 6),
            ("charisma", "How do you read a room?", "Situational Awareness", 60, "Hard", 7),
            ("charisma", "What's your signature move in social settings?", "Authentic Presence", 60, "Medium", 7),
        ]

        await conn.executemany(
            """
            INSERT INTO question_bank (sprint, text, focus, target_seconds, difficulty, day_number)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            seed_data,
        )

        return {"status": "seeded", "count": len(seed_data)}
    finally:
        await conn.close()
