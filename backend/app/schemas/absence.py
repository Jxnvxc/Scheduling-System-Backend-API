from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AbsenceCreate(BaseModel):
    absence_date: str  # YYYY-MM-DD
    reason: Optional[str] = None
    proof_image: Optional[str] = None  # base64 data URL


class AbsenceUpdate(BaseModel):
    reason: Optional[str] = None
    proof_image: Optional[str] = None


class AbsenceApprove(BaseModel):
    note: Optional[str] = None


class AbsenceReject(BaseModel):
    reason: str


class AbsenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    branch_id: int
    absence_date: str
    reason: Optional[str] = None
    proof_image: Optional[str] = None
    status: str
    approved_by: Optional[int] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    employee_name: Optional[str] = None
    approver_name: Optional[str] = None