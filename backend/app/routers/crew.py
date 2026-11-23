from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from collections import defaultdict

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password
from app.database import get_db
from app.models.user import User, UserRole
from app.models.station import Station
from app.models.assignment import ShiftAssignment
from app.schemas.crew import (
    CrewCreate,
    CrewEmployeeNumberUpdate,
    CrewQualifiedStationsUpdate,
    CrewResponse,
)
from app.services.scheduling import period_bounds, shift_hours

DEFAULT_PASSWORD = "janvicPOGI123"
router = APIRouter(prefix="/crew", tags=["Crew Management"])


@router.get("/", response_model=List[CrewResponse])
def get_all_crew(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can manage crew.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    crew = db.query(User).filter(
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).order_by(User.full_name, User.id).all()
    
    return [
        {
            "id": c.id,
            "full_name": c.full_name,
            "email": c.email,
            "employee_number": c.employee_number,
            "role": c.role.value,
            "crew_type": c.crew_type,
            "employment_type": c.employment_type,
            "branch_id": c.branch_id,
            "min_hours": c.min_hours if c.min_hours is not None else 0,
            "max_hours": c.max_hours if c.max_hours is not None else 40,
            "qualified_stations": c.qualified_stations,
            "is_active": c.is_active,
            "worked_hours": c.worked_hours if c.worked_hours is not None else 0.0,
            "created_at": c.created_at
        }
        for c in crew
    ]


@router.get("/hours-summary")
def get_crew_hours_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view crew hours.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    today = date.today()
    period_start, period_end = period_bounds(today)

    assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.status == "Published",
        ShiftAssignment.schedule_date >= period_start,
        ShiftAssignment.schedule_date <= period_end,
    ).all()

    hours_by_user: dict[int, float] = defaultdict(float)
    for assignment in assignments:
        try:
            hours_by_user[assignment.user_id] += shift_hours(
                assignment.shift_name,
                station=None,
                start_time=assignment.start_time,
                end_time=assignment.end_time,
            )
        except Exception:
            # Unknown shift or unparsable time: ignore for the cache.
            hours_by_user.setdefault(assignment.user_id, 0.0)

    crew = db.query(User).filter(
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).order_by(User.full_name, User.id).all()

    crew_summary = []
    for member in crew:
        hours = round(hours_by_user.get(member.id, 0.0), 2)
        member.worked_hours = hours
        crew_summary.append({
            "id": member.id,
            "full_name": member.full_name,
            "worked_hours": hours,
            "min_hours": member.min_hours if member.min_hours is not None else 0,
            "max_hours": member.max_hours if member.max_hours is not None else 40,
        })
    db.commit()

    def _period_label(d: date) -> str:
        return f"{d:%b} {d.day}"

    period_label = f"{_period_label(period_start)} – {_period_label(period_end)}, {period_end.year}"
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": period_label,
        "crew": crew_summary,
    }


@router.get("/assigned-shifts")
def get_crew_assigned_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view crew assigned shifts.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    today = date.today()
    period_start, period_end = period_bounds(today)

    assignments = (
        db.query(ShiftAssignment)
        .join(Station, Station.id == ShiftAssignment.station_id)
        .filter(
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.status == "Published",
            ShiftAssignment.schedule_date >= period_start,
            ShiftAssignment.schedule_date <= period_end,
        )
        .order_by(ShiftAssignment.user_id, ShiftAssignment.schedule_date, ShiftAssignment.start_time)
        .all()
    )

    shifts_by_user: dict[int, list[dict]] = defaultdict(list)
    for assignment in assignments:
        start_time = (
            assignment.start_time.strftime("%H:%M") if assignment.start_time else None
        )
        end_time = (
            assignment.end_time.strftime("%H:%M") if assignment.end_time else None
        )
        shifts_by_user[assignment.user_id].append({
            "schedule_date": assignment.schedule_date.isoformat(),
            "station": assignment.station.name if assignment.station else None,
            "shift_name": assignment.shift_name,
            "start_time": start_time,
            "end_time": end_time,
        })

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "shifts_by_user": {str(k): v for k, v in shifts_by_user.items()},
    }


@router.post("/reset-15-day-hours")
def reset_crew_15_day_hours(
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can reset crew hours.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    crew = db.query(User).filter(
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).all()
    for member in crew:
        member.worked_hours = 0.0
    db.commit()
    return {
        "message": "15-day hours counter reset for all crew in your branch.",
        "reset_count": len(crew),
    }


@router.post("/", response_model=CrewResponse, status_code=status.HTTP_201_CREATED)
def create_crew(
    crew: CrewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can manage crew.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )

    normalized_email = str(crew.email).lower()
    existing = db.query(User.id).filter(
        func.lower(User.email) == normalized_email,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_employee_number = db.query(User.id).filter(
        User.employee_number == crew.employee_number,
    ).first()
    if existing_employee_number:
        raise HTTPException(status_code=409, detail="Employee ID is already assigned.")

    station_ids: list[int] = []
    if crew.qualified_stations:
        try:
            station_ids = list({
                int(station_id.strip())
                for station_id in crew.qualified_stations.split(",")
            })
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Qualified stations must contain valid station IDs.",
            ) from error

        valid_station_count = db.query(Station).filter(
            Station.branch_id == branch_id,
            Station.id.in_(station_ids),
        ).count()
        if valid_station_count != len(station_ids):
            raise HTTPException(
                status_code=422,
                detail="All qualified stations must belong to your assigned branch.",
            )
        
    new_crew = User(
        email=normalized_email,
        employee_number=crew.employee_number,
        password_hash=hash_password(DEFAULT_PASSWORD),
        full_name=crew.full_name,
        role=UserRole.EMPLOYEE,
        crew_type=crew.crew_type,
        employment_type=crew.employment_type,
        branch_id=branch_id,
        min_hours=crew.min_hours,
        max_hours=crew.max_hours,
        qualified_stations=",".join(map(str, station_ids)) or None
    )
    
    db.add(new_crew)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or Employee ID is already in use.",
        ) from error
    db.refresh(new_crew)
    
    return {
        "id": new_crew.id,
        "full_name": new_crew.full_name,
        "email": new_crew.email,
        "employee_number": new_crew.employee_number,
        "role": new_crew.role.value,
        "crew_type": new_crew.crew_type,
        "employment_type": new_crew.employment_type,
        "branch_id": branch_id,
        "min_hours": new_crew.min_hours if new_crew.min_hours is not None else 0,
        "max_hours": new_crew.max_hours if new_crew.max_hours is not None else 40,
        "qualified_stations": new_crew.qualified_stations,
        "is_active": new_crew.is_active,
        "created_at": new_crew.created_at
    }


@router.put(
    "/{crew_id}/employee-number",
    response_model=CrewResponse,
)
def assign_employee_number(
    crew_id: int,
    payload: CrewEmployeeNumberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can manage crew.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )

    crew_member = db.query(User).filter(
        User.id == crew_id,
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
    ).first()
    if crew_member is None:
        raise HTTPException(status_code=404, detail="Crew not found.")

    duplicate = db.query(User.id).filter(
        User.employee_number == payload.employee_number,
        User.id != crew_member.id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Employee ID is already assigned.")

    crew_member.employee_number = payload.employee_number
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Employee ID is already assigned.",
        ) from error
    db.refresh(crew_member)
    return crew_member


@router.put(
    "/{crew_id}/qualified-stations",
    response_model=CrewResponse,
)
def update_qualified_stations(
    crew_id: int,
    payload: CrewQualifiedStationsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can manage crew.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    crew_member = db.query(User).filter(
        User.id == crew_id,
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
    ).first()
    if crew_member is None:
        raise HTTPException(status_code=404, detail="Crew not found.")

    station_ids = sorted(payload.station_ids)
    if station_ids:
        valid_station_count = db.query(Station).filter(
            Station.branch_id == branch_id,
            Station.id.in_(station_ids),
        ).count()
        if valid_station_count != len(station_ids):
            raise HTTPException(
                status_code=422,
                detail="All qualified stations must belong to your assigned branch.",
            )

    crew_member.qualified_stations = ",".join(map(str, station_ids)) or None
    db.commit()
    db.refresh(crew_member)
    return crew_member


@router.delete("/{crew_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crew(
    crew_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can manage crew.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    
    crew_member = db.query(User).filter(
        User.id == crew_id,
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
    ).first()
    if not crew_member:
        raise HTTPException(status_code=404, detail="Crew not found")
    
    db.delete(crew_member)
    db.commit()
    return None