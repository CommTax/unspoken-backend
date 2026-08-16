from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SessionCreate(BaseModel):
    user_id: Optional[str] = None
    user_category: Optional[str] = None

class SessionResponse(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    user_category: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
