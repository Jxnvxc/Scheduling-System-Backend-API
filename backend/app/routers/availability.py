from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import time, date, timedelta

from app.database import get_db
from app.models.availability import Availability
from app.models.assignment import ShiftAssignment
from app.models.user import User, UserRole
from app.schemas.availability import (
    AvailabilityCreate,
    AvailabilityUpdate,
    AvailabilityResponse,
    BulkImportAvailability,
    AvailabilityWindow,
    CrewAvailabilityRequest,
    CrewAvailabilityResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.branch_access import require_manager_branch_id
from app.services.scheduling import _merge_windows

router = APIRouter(prefix="/availability", tags=["Availability"])

# 1. CREW MAG-SET NG AVAILABILITY
@router.post("/", response_model=AvailabilityResponse, status_code=status.HTTP_201_CREATED)
def set_availability(
    avail: AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can set availability")
    
    if avail.end_time <= avail.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    new_avail = Availability(
        user_id=current_user.id,
        day_of_week=avail.day_of_week,
        start_time=avail.start_time,
        end_time=avail.end_time,
        valid_from=avail.valid_from,
        valid_to=avail.valid_to
    )
    db.add(new_avail)
    db.commit()
    db.refresh(new_avail)

    return {**new_avail.__dict__, "full_name": current_user.full_name}

# 2. CREW MAKITA ANG SARILING AVAILABILITY
@router.get("/my", response_model=List[AvailabilityResponse])
def get_my_availability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    availabilities = db.query(Availability).filter(Availability.user_id == current_user.id).all()
    return [
        {**a.__dict__, "full_name": current_user.full_name}
        for a in availabilities
    ]

# 3. I-UPDATE ANG AVAILABILITY (Para sa sudden changes)
@router.put("/{avail_id}", response_model=AvailabilityResponse)
def update_availability(
    avail_id: int,
    avail_update: AvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can update availability")

    avail = db.query(Availability).filter(Availability.id == avail_id, Availability.user_id == current_user.id).first()
    if not avail:
        raise HTTPException(status_code=404, detail="Availability not found")

    update_data = avail_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(avail, key, value)
    
    if avail.end_time <= avail.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    db.commit()
    db.refresh(avail)
    return {**avail.__dict__, "full_name": current_user.full_name}

# 4. I-DELETE ANG AVAILABILITY
@router.delete("/{avail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability(
    avail_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    avail = db.query(Availability).filter(Availability.id == avail_id, Availability.user_id == current_user.id).first()
    if not avail:
        raise HTTPException(status_code=404, detail="Availability not found")
    
    db.delete(avail)
    db.commit()
    return None

# 5. MANAGER: BULK IMPORT AVAILABILITY
@router.post("/bulk-import", status_code=status.HTTP_201_CREATED)
def bulk_import_availability(
    import_data: BulkImportAvailability,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can bulk import availability"
    )

    # `splitlines()` ay na-handle na ang Windows line endings (\r\n),
    # kaya wangging natitir na \r bawat linya.
    lines = import_data.text.strip().splitlines()
    if not lines or not lines[0].strip():
        raise HTTPException(status_code=400, detail="Empty input")

    first_line = lines[0].strip().lower()
    has_header = "employee" in first_line and "day" in first_line
    start_index = 1 if has_header else 0

    created = 0
    updated = 0
    errors = []

    # Tumutukoy sa tunay na linya ng input (i + 1 dahil 1-based ang line number).
    for i in range(start_index, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 6:
            errors.append(f"Line {i + 1}: Expected 6 columns, got {len(parts)}")
            continue

        emp_num, day, start_str, end_str, valid_from_str, valid_to_str = parts

        valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if day not in valid_days:
            errors.append(f"Line {i + 1}: Invalid day '{day}'")
            continue

        try:
            start_time = time.fromisoformat(start_str)
            end_time = time.fromisoformat(end_str)
        except ValueError:
            errors.append(f"Line {i + 1}: Invalid time format (use HH:MM)")
            continue

        try:
            valid_from = date.fromisoformat(valid_from_str)
            valid_to = date.fromisoformat(valid_to_str)
        except ValueError:
            errors.append(f"Line {i + 1}: Invalid date format (use YYYY-MM-DD)")
            continue

        if end_time <= start_time:
            errors.append(f"Line {i + 1}: End time must be after start time")
            continue

        user = db.query(User).filter(
            User.employee_number == emp_num,
            User.branch_id == branch_id,
            User.is_active == True
        ).first()

        if not user:
            errors.append(f"Line {i + 1}: No active crew with Employee ID '{emp_num}' in your branch")
            continue

        existing = db.query(Availability).filter(
            Availability.user_id == user.id,
            Availability.day_of_week == day,
            Availability.valid_from == valid_from
        ).first()

        if existing:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.valid_to = valid_to
            updated += 1
        else:
            new_avail = Availability(
                user_id=user.id,
                day_of_week=day,
                start_time=start_time,
                end_time=end_time,
                valid_from=valid_from,
                valid_to=valid_to
            )
            db.add(new_avail)
            created += 1

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "total_processed": created + updated + len(errors)
    }

# 6. MANAGER: OVERVIEW NG AVAILABILITY NG BUONG CREW (read-only)
@router.get("/overview")
def get_availability_overview(
    week_start: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view crew availability.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )

    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    day_names = [
        (week_start + timedelta(days=i)).strftime("%A") for i in range(7)
    ]
    date_by_day = {
        (week_start + timedelta(days=i)).strftime("%A"): week_start + timedelta(days=i)
        for i in range(7)
    }

    crew = db.query(User).filter(
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).order_by(User.full_name, User.id).all()

    availabilities = db.query(Availability).join(
        User, User.id == Availability.user_id
    ).filter(
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
        Availability.day_of_week.in_(day_names),
    ).all()

    raw_windows: dict[tuple[int, str], list[tuple[time, time]]] = {}
    for a in availabilities:
        day_date = date_by_day.get(a.day_of_week)
        if day_date is None:
            continue
        if not (a.valid_from <= day_date <= a.valid_to):
            continue
        raw_windows.setdefault((a.user_id, a.day_of_week), []).append(
            (a.start_time, a.end_time)
        )

    available_per_day = {name: 0 for name in day_names}
    crew_list = []
    for c in crew:
        days: dict[str, list[dict]] = {}
        for day_name in day_names:
            windows = _merge_windows(raw_windows.get((c.id, day_name), []))
            days[day_name] = [
                {"start": w[0].strftime("%H:%M"), "end": w[1].strftime("%H:%M")}
                for w in windows
            ]
            if windows:
                available_per_day[day_name] += 1
        crew_list.append({
            "id": c.id,
            "full_name": c.full_name,
            "employee_number": c.employee_number,
            "employment_type": c.employment_type,
            "crew_type": c.crew_type,
            "days": days,
            "has_availability": any(days[d] for d in day_names),
        })

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "days": day_names,
        "available_per_day": available_per_day,
        "crew": crew_list,
    }


def _require_crew_employee(
    db: Session,
    employee_id: int,
    branch_id: int,
) -> User:
    employee = db.query(User).filter(
        User.id == employee_id,
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Crew member not found in your branch")
    return employee


def _validate_windows(windows: list[AvailabilityWindow]) -> dict[str, list[tuple[time, time, date, date]]]:
    valid_days = {
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    }
    windows_by_day: dict[str, list[tuple[time, time, date, date]]] = {}
    for idx, w in enumerate(windows):
        label = f"Window {idx + 1}"
        if w.day_of_week not in valid_days:
            raise HTTPException(status_code=400, detail=f"{label}: Invalid day '{w.day_of_week}'")
        if w.end_time <= w.start_time:
            raise HTTPException(
                status_code=400,
                detail=f"{label} ({w.day_of_week}): End time must be after start time",
            )
        if w.valid_to < w.valid_from:
            raise HTTPException(
                status_code=400,
                detail=f"{label} ({w.day_of_week}): valid_to must be on or after valid_from",
            )
        windows_by_day.setdefault(w.day_of_week, []).append(
            (w.start_time, w.end_time, w.valid_from, w.valid_to)
        )

    for day_name, day_windows in windows_by_day.items():
        ordered = sorted(day_windows, key=lambda w: (w[0], w[1]))
        for i in range(1, len(ordered)):
            if ordered[i][0] < ordered[i - 1][1]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Overlapping availability windows on {day_name} "
                    f"around {ordered[i][0].strftime('%H:%M')}",
                )

    return windows_by_day


def _schedule_conflicts(
    employee_id: int,
    windows_by_day: dict[str, list[tuple[time, time, date, date]]],
    db: Session,
) -> list[dict]:
    today = date.today()
    assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.user_id == employee_id,
        ShiftAssignment.status.in_(["Draft", "Published"]),
        ShiftAssignment.schedule_date >= today,
    ).all()

    conflicts: list[dict] = []
    for assignment in assignments:
        day_name = assignment.schedule_date.strftime("%A")
        day_windows = windows_by_day.get(day_name, [])
        covering = [
            (s, e) for s, e, vf, vt in day_windows
            if vf <= assignment.schedule_date <= vt
        ]
        if not covering:
            conflicts.append({
                "date": assignment.schedule_date.isoformat(),
                "day": day_name,
                "shift": assignment.shift_name,
                "start": assignment.start_time.strftime("%H:%M")
                    if assignment.start_time else "—",
                "end": assignment.end_time.strftime("%H:%M")
                    if assignment.end_time else "—",
                "reason": "No availability on this day",
            })
            continue
        merged = _merge_windows(covering)
        shift_start = assignment.start_time
        shift_end = assignment.end_time
        if shift_start is None or shift_end is None:
            continue
        fits = any(
            ws <= shift_start and we >= shift_end
            for ws, we in merged
        )
        if not fits:
            conflicts.append({
                "date": assignment.schedule_date.isoformat(),
                "day": day_name,
                "shift": assignment.shift_name,
                "start": shift_start.strftime("%H:%M"),
                "end": shift_end.strftime("%H:%M"),
                "reason": "Shift no longer fits within availability",
            })

    return conflicts


# 7. MANAGER: READ AVAILABILITY FOR ONE CREW MEMBER
@router.get("/crew/{employee_id}", response_model=CrewAvailabilityResponse)
def get_crew_availability(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view crew availability.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )

    employee = _require_crew_employee(db, employee_id, branch_id)

    today = date.today()
    availabilities = db.query(Availability).filter(
        Availability.user_id == employee_id,
        Availability.valid_to >= today,
    ).order_by(Availability.day_of_week, Availability.start_time).all()

    windows: list[AvailabilityWindow] = [
        AvailabilityWindow(
            day_of_week=a.day_of_week,
            start_time=a.start_time,
            end_time=a.end_time,
            valid_from=a.valid_from,
            valid_to=a.valid_to,
        )
        for a in availabilities
    ]

    return CrewAvailabilityResponse(
        employee_id=employee.id,
        full_name=employee.full_name,
        windows=windows,
    )


# 8. MANAGER: REPLACE AVAILABILITY FOR ONE CREW MEMBER
@router.put("/crew/{employee_id}", response_model=CrewAvailabilityResponse)
def replace_crew_availability(
    employee_id: int,
    request: CrewAvailabilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can update crew availability.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )

    employee = _require_crew_employee(db, employee_id, branch_id)

    today = date.today()
    yesterday = today - timedelta(days=1)

    windows_by_day = _validate_windows(request.windows)

    conflicts = _schedule_conflicts(employee_id, windows_by_day, db)
    if conflicts and not request.confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "conflicts": conflicts,
                "message": "Some existing shifts would no longer fit the new availability. Confirm to proceed.",
            },
        )

    # Close old active entries (history preservation), then create new ones.
    active = db.query(Availability).filter(
        Availability.user_id == employee_id,
        Availability.valid_to >= today,
    ).all()
    for a in active:
        a.valid_to = yesterday

    for w in request.windows:
        db.add(Availability(
            user_id=employee_id,
            day_of_week=w.day_of_week,
            start_time=w.start_time,
            end_time=w.end_time,
            valid_from=w.valid_from,
            valid_to=w.valid_to,
        ))

    db.commit()

    return CrewAvailabilityResponse(
        employee_id=employee.id,
        full_name=employee.full_name,
        windows=request.windows,
    )