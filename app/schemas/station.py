from pydantic import BaseModel
from typing import Optional

class StationCreate(BaseModel):
    branch_id: int
    name: str

class StationResponse(BaseModel):
    id: int
    branch_id: int
    name: str
    branch_name: Optional[str] = None

    class Config:
        from_attributes = True