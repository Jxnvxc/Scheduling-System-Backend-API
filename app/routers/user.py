from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import user_service
from app.auth.jwt_handler import create_access_token
from app.auth.hashing import hash_password, verify_password
from app.auth.dependencies import get_current_user
from app.models.user import User, UserRole  # <-- Idinagdag ang UserRole
from app.schemas.user import UserCreate, UserResponse, UserLogin, ChangePassword, ManagerCreate # <-- Idinagdag ang ManagerCreate

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = user_service.get_user_by_email(db, email=user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    new_user = user_service.create_user(db=db, user=user)
    return new_user

@router.post("/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    authenticated_user = user_service.authenticate_user(db, email=user.email, password=user.password)
    if not authenticated_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    token_data = {
        "sub": authenticated_user.email,
        "role": authenticated_user.role.value
    }
    access_token = create_access_token(data=token_data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": authenticated_user.id,
            "email": authenticated_user.email,
            "full_name": authenticated_user.full_name,
            "role": authenticated_user.role.value,
            "branch_id": authenticated_user.branch_id # <-- BAGO: Para malaman ng frontend ang branch niya
        }
    }

@router.post("/change-password")
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # I-verify ang lumang password
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect"
        )
    
    # I-validate ang bagong password
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters"
        )
    
    # I-update ang password
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Password changed successfully!"}

# ==========================================
# BAGONG ENDPOINT: ADMIN CREATES MANAGER
# ==========================================
@router.post("/create-manager", status_code=status.HTTP_201_CREATED)
def create_manager(
    manager: ManagerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Tanging Admin lang ang pwedeng gumawa ng Manager
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only Admin can create Managers"
        )

    # Check kung existing ang email
    existing = db.query(User).filter(User.email == manager.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Gumawa ng bagong Manager na naka-link sa Branch
    new_manager = User(
        email=manager.email,
        password_hash=hash_password(manager.password),
        full_name=manager.full_name,
        role=UserRole.MANAGER,
        branch_id=manager.branch_id
    )
    
    db.add(new_manager)
    db.commit()
    db.refresh(new_manager)

    return {"message": "Manager created successfully!", "manager_id": new_manager.id}