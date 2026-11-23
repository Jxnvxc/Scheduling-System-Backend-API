from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STANDARD_SHIFT_NAMES = ("Opening", "Mid", "Closing")


class StaffingRequirementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: int = Field(gt=0)
    shift_type: str = Field(min_length=1, max_length=100)
    start_time: time
    end_time: time
    required_count: int = Field(ge=0, le=100)
    minimum_crew: Optional[int] = Field(default=None, ge=0, le=100)
    enabled: bool = True

    @field_validator("shift_type")
    @classmethod
    def normalize_shift_type(cls, value: str) -> str:
        normalized = value.strip()
        canonical_names = {
            name.casefold(): name for name in STANDARD_SHIFT_NAMES
        }
        try:
            return canonical_names[normalized.casefold()]
        except KeyError as error:
            raise ValueError(
                "Shift name must be Opening, Mid, or Closing."
            ) from error

    @model_validator(mode="after")
    def validate_shift_times(self) -> "StaffingRequirementUpdate":
        if self.end_time <= self.start_time:
            raise ValueError("Shift end time must be later than its start time.")
        return self

    @model_validator(mode="after")
    def validate_minimum_crew(self) -> "StaffingRequirementUpdate":
        if (
            self.minimum_crew is not None
            and self.minimum_crew > self.required_count
        ):
            raise ValueError(
                "Minimum crew cannot be greater than required crew."
            )
        return self


class StaffingRequirementBulkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[StaffingRequirementUpdate] = Field(max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_station_shifts(self) -> "StaffingRequirementBulkUpdate":
        keys = [
            (item.station_id, item.shift_type.casefold())
            for item in self.requirements
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("A station shift can only appear once.")
        return self


class StaffingRequirementResponse(BaseModel):
    station_id: int
    station_name: str
    shift_type: str
    start_time: time
    end_time: time
    required_count: int
    minimum_crew: Optional[int] = None
    enabled: bool
