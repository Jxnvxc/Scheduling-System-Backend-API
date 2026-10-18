from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.schemas.branch import BranchCreate, BranchResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/branches", tags=["Branches"])

@router.post("/", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
def create_branch(
    branch: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized to create branches")

    existing = db.query(Branch).filter(Branch.name == branch.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Branch name already exists")

    new_branch = Branch(
        name=branch.name,
        opening_time=branch.opening_time,
        closing_time=branch.closing_time,
        prep_time_minutes=branch.prep_time_minutes,
        closing_time_minutes=branch.closing_time_minutes
    )
    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)
    return new_branch

@router.get("/", response_model=List[BranchResponse])
def get_all_branches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized to view branches")

    return db.query(Branch).all()