from pydantic import BaseModel, EmailStr, Field 
from typing import Optional
from datetime import datetime
from sqlalchemy import true
from app.models.user import UserRole


class UserBase(BaseModel):
  email: EmailStr
  full_name: str = Field(..., min_length = 2, max_length = 100)
  role: UserRole = UserRole.EMPLOYEE 

class UserCreate(UserBase): 
  password: str = Field(..., min_length=8, max_length=50)


class UserResponse(BaseModel):
  id: int
  is_Active: bool
  created_at : datetime
  update_at: Optional[datetime] = None

  class config:
    from_attributes = true

class UserLogin(BaseModel):
    email: EmailStr
    password: str




  



   