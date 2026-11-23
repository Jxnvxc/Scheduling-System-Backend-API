from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StationShiftHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    opening_start_time: time = time(8, 0)
    opening_end_time: time = time(16, 0)
    mid_start_time: time = time(12, 0)
    mid_end_time: time = time(20, 0)
    closing_start_time: time = time(14, 0)
    closing_end_time: time = time(22, 0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Station name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_shift_hours(self) -> "StationShiftHours":
        shifts = (
            ("Opening", self.opening_start_time, self.opening_end_time),
            ("Mid", self.mid_start_time, self.mid_end_time),
            ("Closing", self.closing_start_time, self.closing_end_time),
        )
        for shift_name, start_time, end_time in shifts:
            if end_time <= start_time:
                raise ValueError(
                    f"{shift_name} end time must be later than its start time."
                )
        return self


class StationCreate(StationShiftHours):
    priority: int = Field(default=2, ge=1, le=3)

class StationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    opening_start_time: Optional[time] = None
    opening_end_time: Optional[time] = None
    mid_start_time: Optional[time] = None
    mid_end_time: Optional[time] = None
    closing_start_time: Optional[time] = None
    closing_end_time: Optional[time] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Station name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_shift_hours(self) -> "StationUpdate":
        shifts = (
            ("Opening", self.opening_start_time, self.opening_end_time),
            ("Mid", self.mid_start_time, self.mid_end_time),
            ("Closing", self.closing_start_time, self.closing_end_time),
        )
        for shift_name, start_time, end_time in shifts:
            if (start_time is None) != (end_time is None):
                raise ValueError(
                    f"{shift_name} start and end times must be provided together."
                )
            if start_time is not None and end_time is not None and end_time <= start_time:
                raise ValueError(
                    f"{shift_name} end time must be later than its start time."
                )
        return self


class StationResponse(BaseModel):
    id: int
    branch_id: int
    name: str
    opening_start_time: time
    opening_end_time: time
    mid_start_time: time
    mid_end_time: time
    closing_start_time: time
    closing_end_time: time
    priority: int = 2
    branch_name: Optional[str] = None

    class Config:
        from_attributes = True