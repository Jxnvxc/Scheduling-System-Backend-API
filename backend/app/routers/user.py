from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.jwt_handler import create_access_token
from app.auth.hashing import verify_password
from app.auth.dependencies import get_current_user
from app.models.user import User, UserRole
from app.schemas.user import ChangePassword, UserLogin, UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

# Public registration disabled. Crew accounts are created by Managers via email.
# @router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
# def register_user(user: UserCreate, db: Session = Depends(get_db)):
#     existing_user = user_service.get_user_by_email(db, email=user.email)
#     if existing_user:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Email already registered"
#         )
#     new_user = user_service.create_user(db=db, user=user)
#     return new_user

@router.post("/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    role_by_account_type = {
        "employee": UserRole.EMPLOYEE,
        "manager": UserRole.MANAGER,
        "head": UserRole.HEAD,
    }
    query = db.query(User).filter(
        func.lower(User.email) == str(user.email).lower(),
        User.role == role_by_account_type[user.account_type],
    )
    if user.account_type == "employee":
        query = query.filter(User.employee_number == user.employee_number)
    elif user.account_type == "manager":
        query = query.filter(User.manager_id == user.manager_id)

    authenticated_user = query.first()
    if (
        authenticated_user is not None
        and (
            not authenticated_user.password_hash
            or not verify_password(user.password, authenticated_user.password_hash)
        )
    ):
        authenticated_user = None
    if not authenticated_user or not authenticated_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login details"
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
            "branch_id": authenticated_user.branch_id,
        }
    }


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # I-verify ang lumang password
    if not current_user.password_hash or not verify_password(
        payload.old_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect"
        )
    
    # I-update ang password
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Password changed successfully!"}
