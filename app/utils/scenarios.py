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
