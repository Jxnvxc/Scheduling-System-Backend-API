from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.crew import CrewCreate, CrewResponse
from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password

DEFAULT_PASSWORD = "janvicPOGI123"
router = APIRouter(prefix="/crew", tags=["Crew Management"])


@router.get("/", response_model=List[CrewResponse])
def get_all_crew(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only managers and admins can view crew")
    
    crew = db.query(User).filter(User.role == UserRole.EMPLOYEE).all()
    
    return [
        {
            "id": c.id,
            "full_name": c.full_name,
            "email": c.email,
            "role": c.role.value,
            "crew_type": c.crew_type,
            "employment_type": c.employment_type,
            "is_active": c.is_active,
            "created_at": c.created_at
        }
        for c in crew
    ]


@router.post("/", response_model=CrewResponse, status_code=status.HTTP_201_CREATED)
def create_crew(
    crew: CrewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only managers and admins can create crew")
    
    existing = db.query(User).filter(User.email == crew.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_crew = User(
       email=crew.email,
       password_hash=hash_password(DEFAULT_PASSWORD),  # ← BAGO
       full_name=crew.full_name,
       role=UserRole.EMPLOYEE,
       crew_type=crew.crew_type,
       employment_type=crew.employment_type
)
    
    db.add(new_crew)
    db.commit()
    db.refresh(new_crew)
    
    return {
        "id": new_crew.id,
        "full_name": new_crew.full_name,
        "email": new_crew.email,
        "role": new_crew.role.value,
        "crew_type": new_crew.crew_type,
        "employment_type": new_crew.employment_type,
        "is_active": new_crew.is_active,
        "created_at": new_crew.created_at
    }


@router.delete("/{crew_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crew(
    crew_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Only managers and admins can delete crew")
    
    crew = db.query(User).filter(User.id == crew_id, User.role == UserRole.EMPLOYEE).first()
    if not crew:
        raise HTTPException(status_code=404, detail="Crew not found")
    
    db.delete(crew)
    db.commit()
    return None