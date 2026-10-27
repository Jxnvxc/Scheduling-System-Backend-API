from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, date, time
from pydantic import BaseModel

from app.database import get_db
from app.models.schedule import Schedule
from app.models.assignment import ShiftAssignment
from app.models.user import User, UserRole
from app.models.station import Station
from app.models.requirement import StaffingRequirement
from app.models.availability import Availability
from app.schemas.schedule import ScheduleResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/schedules", tags=["Schedules"])

class PublishItem(BaseModel):
    user_id: int
    station_id: int
    shift_name: str

class PublishRequest(BaseModel):
    branch_id: int
    schedule_date: date
    assignments: List[PublishItem]

@router.get("/", response_model=List[ScheduleResponse])
def get_all_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")
    schedules = db.query(Schedule).all()
    return [
        {
            "id": s.id,
            "manager_id": s.manager_id,
            "manager_name": s.manager.full_name if s.manager else "Unknown",
            "branch_name": s.branch_name,
            "schedule_date": s.schedule_date,
            "shift_start": s.shift_start,
            "shift_end": s.shift_end,
            "status": s.status,
            "created_at": s.created_at
        }
        for s in schedules
    ]

@router.post("/generate-full-day")
def generate_full_day(
    branch_id: int,
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    stations = db.query(Station).filter(Station.branch_id == branch_id).all()
    day_name = schedule_date.strftime("%A")
    
    employees = db.query(User).filter(
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active == True
    ).all()

    print(f"\n--- GENERATING FOR {day_name}, {schedule_date} ---")
    print(f"Total Employees sa Branch: {len(employees)}")

    assigned_employee_ids = set() 
    generated_schedule = []

    shifts = {
        "Opening": {"start": time(8, 0), "end": time(16, 0), "display": "08:00 - 16:00"},
        "Mid":     {"start": time(12, 0), "end": time(20, 0), "display": "12:00 - 20:00"},
        "Closing": {"start": time(14, 0), "end": time(22, 0), "display": "14:00 - 22:00"}
    }

    for station in stations:
        for shift_name, times in shifts.items():
            req = db.query(StaffingRequirement).filter(
                StaffingRequirement.station_id == station.id,
                StaffingRequirement.shift_type == shift_name
            ).first()
            
            needed = req.required_count if req else 1
            assigned_for_this_shift = []

            for emp in employees:
                if len(assigned_for_this_shift) >= needed:
                    break 
                
                if emp.id in assigned_employee_ids:
                    continue 

                # --- 1. CHECK SKILLS ---
                is_qualified = False
                if emp.qualified_stations:
                    # Hatiin sa comma, tapos alisin ang spaces (.strip()), tapos gawing list
                    station_ids = [s.strip() for s in emp.qualified_stations.split(',')]
                    if str(station.id) in station_ids:
                        is_qualified = True

                # --- 2. CHECK AVAILABILITY ---
                avail = db.query(Availability).filter(
                    Availability.user_id == emp.id,
                    Availability.day_of_week == day_name,
                    Availability.valid_from <= schedule_date,
                    Availability.valid_to >= schedule_date,
                    Availability.start_time <= times["start"],
                    Availability.end_time >= times["end"]
                ).first()

                # --- DEBUG PRINT (Para makita natin sa terminal kung bakit bagsak) ---
                if is_qualified and not avail:
                    print(f"❌ {emp.full_name} is qualified for {station.name}, BUT NOT AVAILABLE on {day_name} {times['display']}")
                
                if is_qualified and avail:
                    print(f"✅ ASSIGNED: {emp.full_name} to {station.name} ({shift_name})")
                    assigned_for_this_shift.append({"id": emp.id, "name": emp.full_name})
                    assigned_employee_ids.add(emp.id)

            generated_schedule.append({
                "station_id": station.id,
                "station": station.name,
                "shift": shift_name,
                "time": times["display"],
                "needed": needed,
                "assigned": assigned_for_this_shift,
                "status": "Complete" if len(assigned_for_this_shift) == needed else "Shortage"
            })

    return {"date": schedule_date, "branch_id": branch_id, "schedule": generated_schedule}

@router.post("/publish")
def publish_schedule(
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == payload.branch_id,
        ShiftAssignment.schedule_date == payload.schedule_date
    ).delete(synchronize_session=False)

    for item in payload.assignments:
        new_assignment = ShiftAssignment(
            user_id=item.user_id,
            branch_id=payload.branch_id,
            station_id=item.station_id,
            schedule_date=payload.schedule_date,
            shift_name=item.shift_name,
            status="Published"
        )
        db.add(new_assignment)
    
    db.commit()
    return {"message": "Schedule published successfully! 🎉"}