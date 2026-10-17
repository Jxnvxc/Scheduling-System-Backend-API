from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# Para sa pag-create ng crew
class CrewCreate(BaseModel):
    full_name: str
    email: EmailStr
    crew_type: str          # e.g., "Gel crew, Crew Trainer"
    employment_type: str    # "Full-time" o "Part-time"
# Para sa response (hindi kasama ang password)
class CrewResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True