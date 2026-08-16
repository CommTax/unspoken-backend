from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    full_name: str
    email: str
    whatsapp: Optional[str] = None

class UserResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    whatsapp: Optional[str] = None
    created_at: datetime
