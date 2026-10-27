from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class CrewCreate(BaseModel):
    full_name: str
    email: EmailStr
    employment_type: str
    crew_type: str
    branch_id: Optional[int] = None
    min_hours: Optional[int] = 0
    max_hours: Optional[int] = 40
    qualified_stations: Optional[str] = None

class CrewResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    crew_type: Optional[str] = None
    employment_type: Optional[str] = None
    branch_id: Optional[int] = None
    min_hours: Optional[int] = 0   # <-- Ginawang Optional
    max_hours: Optional[int] = 40  # <-- Ginawang Optional
    qualified_stations: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ManagerCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    branch_id: int