from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schedule import Schedule
from app.models.user import User, UserRole
from app.schemas.schedule import ScheduleResponse, ScheduleCreate
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/schedules", tags=["Schedules"])

@router.get("/", response_model=List[ScheduleResponse])
def get_all_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Admin at Manager lang ang pwedeng makakita ng lahat ng schedules
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view schedules"
        )
    
    schedules = db.query(Schedule).all()
    
    result = []
    for s in schedules:
        result.append({
            "id": s.id,
            "manager_id": s.manager_id,
            "manager_name": s.manager.full_name if s.manager else "Unknown Manager",
            "branch_name": s.branch_name,
            "schedule_date": s.schedule_date,
            "shift_start": s.shift_start,
            "shift_end": s.shift_end,
            "status": s.status,
            "created_at": s.created_at
        })
    
    return result

@router.post("/", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    schedule: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Manager at Admin lang ang pwedeng gumawa ng schedule
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers and admins can create schedules"
        )
    
    new_schedule = Schedule(
        manager_id=current_user.id,
        branch_name=schedule.branch_name,
        schedule_date=schedule.schedule_date,
        shift_start=schedule.shift_start,
        shift_end=schedule.shift_end,
        status="Draft"
    )
    
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)
    
    return {
        "id": new_schedule.id,
        "manager_id": new_schedule.manager_id,
        "manager_name": current_user.full_name,
        "branch_name": new_schedule.branch_name,
        "schedule_date": new_schedule.schedule_date,
        "shift_start": new_schedule.shift_start,
        "shift_end": new_schedule.shift_end,
        "status": new_schedule.status,
        "created_at": new_schedule.created_at
    }