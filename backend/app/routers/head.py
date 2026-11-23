from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.schemas.branch import BranchCreate, BranchResponse
from app.schemas.head import (
    HeadManagerCreate,
    HeadManagerUpdate,
    ManagerBranchAssignment,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/head", tags=["Head Management"])


def _require_head(current_user: User) -> None:
    if current_user.role != UserRole.HEAD:
        raise HTTPException(status_code=403, detail="Only Head accounts can manage managers.")


@router.get("/branches", response_model=list[BranchResponse])
def list_branches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)
    return db.query(Branch).order_by(Branch.name).all()


@router.post(
    "/branches",
    response_model=BranchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_branch(
    payload: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)

    normalized_name = payload.name.strip()
    existing_branch = db.query(Branch.id).filter(
        func.lower(Branch.name) == normalized_name.lower(),
    ).first()
    if existing_branch:
        raise HTTPException(status_code=409, detail="A branch with that name already exists.")

    branch = Branch(
        name=normalized_name,
        opening_time=payload.opening_time,
        closing_time=payload.closing_time,
        prep_time_minutes=payload.prep_time_minutes,
        closing_time_minutes=payload.closing_time_minutes,
    )
    db.add(branch)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A branch with that name already exists.",
        ) from error

    db.refresh(branch)
    return branch


@router.get("/managers", response_model=list[UserResponse])
def list_managers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)
    return (
        db.query(User)
        .filter(
            User.role == UserRole.MANAGER,
            User.is_active.is_(True),
        )
        .order_by(User.full_name, User.id)
        .all()
    )


@router.post(
    "/managers",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_manager(
    payload: HeadManagerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)

    branch = db.query(Branch).filter(Branch.id == payload.branch_id).first()
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found.")

    normalized_email = str(payload.email).lower()
    existing_user = db.query(User.id).filter(
        func.lower(User.email) == normalized_email,
    ).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    existing_manager_id = db.query(User.id).filter(
        User.manager_id == payload.manager_id,
    ).first()
    if existing_manager_id:
        raise HTTPException(status_code=409, detail="That Manager ID is already in use.")

    manager = User(
        email=normalized_email,
        manager_id=payload.manager_id,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.MANAGER,
        branch_id=branch.id,
        is_active=True,
    )
    db.add(manager)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That email or Manager ID is already in use.",
        ) from error

    db.refresh(manager)
    return manager


@router.put("/managers/{manager_id}", response_model=UserResponse)
def update_manager(
    manager_id: int,
    payload: HeadManagerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)

    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == UserRole.MANAGER,
        User.is_active.is_(True),
    ).first()
    if manager is None:
        raise HTTPException(status_code=404, detail="Manager account not found.")

    updates = payload.model_dump(exclude_unset=True)
    branch_id = updates.get("branch_id")
    if branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if branch is None:
            raise HTTPException(status_code=404, detail="Branch not found.")

    email = updates.get("email")
    if email is not None:
        normalized_email = str(email).lower()
        duplicate_email = db.query(User.id).filter(
            func.lower(User.email) == normalized_email,
            User.id != manager.id,
        ).first()
        if duplicate_email:
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        updates["email"] = normalized_email

    updated_manager_id = updates.get("manager_id")
    if updated_manager_id is not None:
        duplicate_manager_id = db.query(User.id).filter(
            User.manager_id == updated_manager_id,
            User.id != manager.id,
        ).first()
        if duplicate_manager_id:
            raise HTTPException(status_code=409, detail="That Manager ID is already in use.")

    password = updates.pop("password", None)
    if password is not None:
        updates["password_hash"] = hash_password(password)

    for field, value in updates.items():
        setattr(manager, field, value)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That email or Manager ID is already in use.",
        ) from error

    db.refresh(manager)
    return manager


@router.put("/managers/{manager_id}/branch", response_model=UserResponse)
def assign_manager_branch(
    manager_id: int,
    assignment: ManagerBranchAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_head(current_user)

    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == UserRole.MANAGER,
        User.is_active.is_(True),
    ).first()
    if manager is None:
        raise HTTPException(status_code=404, detail="Manager account not found.")

    branch = db.query(Branch).filter(Branch.id == assignment.branch_id).first()
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found.")

    manager.branch_id = branch.id
    db.commit()
    db.refresh(manager)
    return manager
