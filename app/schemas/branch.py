from pydantic import BaseModel
from datetime import time
from typing import Optional

class BranchCreate(BaseModel):
    name: str
    opening_time: time
    closing_time: time
    prep_time_minutes: Optional[int] = 30
    closing_time_minutes: Optional[int] = 30

class BranchResponse(BaseModel):
    id: int
    name: str
    opening_time: time
    closing_time: time
    prep_time_minutes: int
    closing_time_minutes: int

    class Config:
        from_attributes = True