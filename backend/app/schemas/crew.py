from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

class CrewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    employee_number: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")
    employment_type: Literal["Full-time", "Part-time"]
    crew_type: str = Field(min_length=1, max_length=255)
    min_hours: int = Field(default=40, ge=0, le=168)
    max_hours: int = Field(default=80, ge=0, le=168)
    qualified_stations: str | None = None

    @field_validator("full_name", "crew_type")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be blank.")
        return normalized

    @field_validator("employee_number", mode="before")
    @classmethod
    def trim_employee_number(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_weekly_hours(self) -> "CrewCreate":
        if self.min_hours > self.max_hours:
            raise ValueError("Minimum hours cannot exceed maximum hours.")
        return self


class CrewEmployeeNumberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")

    @field_validator("employee_number", mode="before")
    @classmethod
    def trim_employee_number(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class CrewQualifiedStationsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_ids: list[PositiveInt] = Field(max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_stations(self) -> "CrewQualifiedStationsUpdate":
        if len(self.station_ids) != len(set(self.station_ids)):
            raise ValueError("A station can only be selected once.")
        return self


class CrewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    employee_number: str | None = None
    role: str
    crew_type: str | None = None
    employment_type: str | None = None
    branch_id: int | None = None
    min_hours: int = 40
    max_hours: int = 80
    qualified_stations: str | None = None
    is_active: bool
    worked_hours: float = 0.0
    created_at: datetime


class ManagerCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    branch_id: int