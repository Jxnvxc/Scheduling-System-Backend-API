from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserRole
from app.models.schedule import Schedule
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("/manager")
def get_manager_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Bilangin ang lahat ng employees (crew) sa system
    team_members = db.query(User).filter(User.role == UserRole.EMPLOYEE).count()
    
    # Sa ngayon, zero muna ang iba dahil wala pa tayong availability logic
    # Bibigyan natin ito ng totoong logic sa susunod na steps
    todays_staff = 0
    coverage = "0%"
    conflicts = 0
    
    return {
        "team_members": team_members,
        "todays_staff": todays_staff,
        "coverage": coverage,
        "conflicts": conflicts
    }