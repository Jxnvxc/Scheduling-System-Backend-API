from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_date_range(self) -> "LeaveRequestCreate":
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date.")
        return self


class SwapRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requester_assignment_id: int = Field(gt=0)
    target_assignment_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reject_same_assignment(self) -> "SwapRequestCreate":
        if self.requester_assignment_id == self.target_assignment_id:
            raise ValueError("Choose two different shifts to swap.")
        return self


class SwapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: bool


class ManagerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
