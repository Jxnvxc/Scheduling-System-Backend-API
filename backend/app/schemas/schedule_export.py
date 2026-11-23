from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScheduleExportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: int = Field(gt=0)
    shift_name: str = Field(min_length=1, max_length=100)
    assigned_user_ids: list[int] = Field(max_length=100)

    @field_validator("shift_name")
    @classmethod
    def normalize_shift_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Shift name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def reject_duplicate_assignees(self) -> "ScheduleExportRow":
        if len(self.assigned_user_ids) != len(set(self.assigned_user_ids)):
            raise ValueError("A crew member can only be assigned once per shift.")
        return self


class ScheduleExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_date: date
    rows: list[ScheduleExportRow] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_station_shifts(self) -> "ScheduleExportRequest":
        keys = [
            (row.station_id, row.shift_name.casefold())
            for row in self.rows
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("A station shift can only appear once.")

        assignee_ids = [
            user_id for row in self.rows for user_id in row.assigned_user_ids
        ]
        if len(assignee_ids) != len(set(assignee_ids)):
            raise ValueError("A crew member can only be scheduled once per day.")
        return self
