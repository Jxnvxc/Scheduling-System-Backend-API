from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    opening_time: time
    closing_time: time
    prep_time_minutes: int = Field(default=30, ge=0, le=1440)
    closing_time_minutes: int = Field(default=30, ge=0, le=1440)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Branch name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_operating_hours(self) -> "BranchCreate":
        if self.opening_time >= self.closing_time:
            raise ValueError("Closing time must be later than opening time.")
        return self

class BranchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    opening_time: time
    closing_time: time
    prep_time_minutes: int
    closing_time_minutes: int
