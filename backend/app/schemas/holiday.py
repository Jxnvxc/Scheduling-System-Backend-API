from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict


class HolidayBase(BaseModel):
    holiday_date: date
    name: str
    holiday_type: str


class HolidayCreate(HolidayBase):
    model_config = ConfigDict(extra="forbid")


class HolidayResponse(HolidayBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: Optional[int] = None


class HolidayDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holiday_id: int


VALID_HOLIDAY_TYPES = {
    "Regular Working",
    "Regular Holiday",
    "Special Non-Working",
    "Special Working",
}
