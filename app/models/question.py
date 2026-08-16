from pydantic import BaseModel
from typing import Optional, List

class Option(BaseModel):
    label: str
    value: str
    sub: Optional[str] = None

class QuestionResponse(BaseModel):
    question_code: str
    question_text: str
    options: Optional[List[dict]] = None
    is_voice: Optional[bool] = False
    voice_prompt: Optional[str] = None
