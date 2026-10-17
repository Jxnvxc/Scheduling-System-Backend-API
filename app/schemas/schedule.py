from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Para sa POST request
class ScheduleCreate(BaseModel):
    branch_name: str
    schedule_date: str
    shift_start: str
    shift_end: str

# Para sa response
class ScheduleResponse(BaseModel):
    id: int
    manager_id: int
    manager_name: Optional[str] = None
    branch_name: str
    schedule_date: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True