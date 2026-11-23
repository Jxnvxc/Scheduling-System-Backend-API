from typing import Literal, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    account_type: Literal["employee", "manager", "head"] = "employee"
    employee_number: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+$",
    )
    manager_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+$",
    )

    @model_validator(mode="after")
    def validate_role_identifier(self):
        if self.account_type == "employee":
            if self.employee_number is None:
                raise ValueError("Crew registration requires an Employee Number.")
            if not self.employee_number.isdigit():
                raise ValueError("Employee Number must contain digits only.")
            if self.manager_id is not None:
                raise ValueError("Crew registration should not include a Manager ID.")
        elif self.account_type == "manager":
            if self.manager_id is None:
                raise ValueError("Manager registration requires a Manager ID.")
            if not self.manager_id.isdigit():
                raise ValueError("Manager ID must contain digits only.")
            if self.employee_number is not None:
                raise ValueError("Manager registration should not include an Employee Number.")
        elif self.employee_number is not None or self.manager_id is not None:
            raise ValueError("Head registration does not use a staff ID.")
        return self

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    manager_id: Optional[str] = None
    employee_number: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)
    account_type: Literal["employee", "manager", "head"]
    employee_number: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+$",
    )
    manager_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+$",
    )

    @model_validator(mode="after")
    def validate_role_identifier(self):
        if self.account_type == "employee":
            if self.employee_number is None or self.manager_id is not None:
                raise ValueError("Crew login requires an Employee Number only.")
            if not self.employee_number.isdigit():
                raise ValueError("Employee Number must contain digits only.")
        elif self.account_type == "manager":
            if self.manager_id is None or self.employee_number is not None:
                raise ValueError("Manager login requires a Manager ID only.")
            if not self.manager_id.isdigit():
                raise ValueError("Manager ID must contain digits only.")
        elif self.employee_number is not None or self.manager_id is not None:
            raise ValueError("Head login does not use a staff ID.")
        return self

class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)