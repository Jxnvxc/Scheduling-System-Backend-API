from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.auth.hashing import hash_password, verify_password

def create_user(db: Session, user: UserCreate):
    hashed_password = hash_password(user.password)
    role_map = {
        "employee": UserRole.EMPLOYEE,
        "manager": UserRole.MANAGER,
        "head": UserRole.HEAD,
    }
    db_user = User(
        email=user.email,
        password_hash=hashed_password,
        full_name=user.full_name,
        role=role_map[user.account_type],
        employee_number=user.employee_number,
        manager_id=user.manager_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return False
    if not user.password_hash or not verify_password(password, user.password_hash):
        return False
    return user