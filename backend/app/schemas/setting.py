from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SystemSettingBase(BaseModel):
    key: str
    value: str


class SystemSettingCreate(SystemSettingBase):
    model_config = ConfigDict(extra="forbid")
    branch_id: Optional[int] = None


class SystemSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class SystemSettingResponse(SystemSettingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: Optional[int] = None


PRE_HOLIDAY_MIRROR_KEY = "pre_holiday_mirror_enabled"
PRE_HOLIDAY_MIRROR_ON = "ON"
PRE_HOLIDAY_MIRROR_OFF = "OFF"
