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
    
    # I-SECURITY CHECK: Data Isolation
    query = db.query(User).filter(User.role == UserRole.EMPLOYEE)
    
    if current_user.role == UserRole.MANAGER:
        # Kita lang ni Manager yung crew sa branch niya
        query = query.filter(User.branch_id == current_user.branch_id)

    crew = query.all()
    
    return [
        {
            "id": c.id,
            "full_name": c.full_name,
            "email": c.email,
            "role": c.role.value,
            "crew_type": c.crew_type,
            "employment_type": c.employment_type,
            "branch_id": c.branch_id,
            "min_hours": c.min_hours if c.min_hours is not None else 0,
            "max_hours": c.max_hours if c.max_hours is not None else 40,
            "qualified_stations": c.qualified_stations,
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
    
    # I-SECURITY CHECK: Manager can only create crew for their own branch
    if current_user.role == UserRole.MANAGER and crew.branch_id != current_user.branch_id:
        raise HTTPException(status_code=403, detail="You can only create crew for your assigned branch")

    existing = db.query(User).filter(User.email == crew.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_crew = User(
        email=crew.email,
        password_hash=hash_password(DEFAULT_PASSWORD),
        full_name=crew.full_name,
        role=UserRole.EMPLOYEE,
        crew_type=crew.crew_type,
        employment_type=crew.employment_type,
        branch_id=crew.branch_id,
        min_hours=crew.min_hours,
        max_hours=crew.max_hours,
        qualified_stations=crew.qualified_stations
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
        "branch_id": new_crew.branch_id,
        "min_hours": new_crew.min_hours if new_crew.min_hours is not None else 0,
        "max_hours": new_crew.max_hours if new_crew.max_hours is not None else 40,
        "qualified_stations": new_crew.qualified_stations,
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
    
    crew_member = db.query(User).filter(User.id == crew_id, User.role == UserRole.EMPLOYEE).first()
    if not crew_member:
        raise HTTPException(status_code=404, detail="Crew not found")

    # I-SECURITY CHECK: Manager can only delete crew from their own branch
    if current_user.role == UserRole.MANAGER and crew_member.branch_id != current_user.branch_id:
        raise HTTPException(status_code=403, detail="You can only delete crew from your assigned branch")
    
    db.delete(crew_member)
    db.commit()
    return None