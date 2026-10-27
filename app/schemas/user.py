from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# ==========================================
# MGA EXISTING SCHEMAS
# ==========================================
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "employee"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    branch_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ChangePassword(BaseModel):
    old_password: str
    new_password: str

# ==========================================
# BAGONG SCHEMA PARA SA MANAGER CREATION
# ==========================================
class ManagerCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    branch_id: int