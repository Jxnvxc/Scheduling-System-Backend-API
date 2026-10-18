from pydantic import BaseModel
from datetime import date, time
from typing import Optional

class AvailabilityCreate(BaseModel):
    day_of_week: str
    start_time: time
    end_time: time
    valid_from: date
    valid_to: date

class AvailabilityUpdate(BaseModel):
    day_of_week: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None

class AvailabilityResponse(BaseModel):
    id: int
    user_id: int
    day_of_week: str
    start_time: time
    end_time: time
    valid_from: date
    valid_to: date
    full_name: Optional[str] = None

    class Config:
        from_attributes = True