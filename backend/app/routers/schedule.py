from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime, time, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field
import time
import uuid
import threading
from functools import lru_cache

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db, SessionLocal
from app.models.schedule import Schedule
from app.models.branch import Branch
from app.models.assignment import ShiftAssignment
from app.models.user import User, UserRole
from app.models.station import Station
from app.models.requirement import StaffingRequirement
from app.models.availability import Availability
from app.models.crew_request import CrewRequest
from app.models.absence import Absence, AbsenceStatus
from app.models.holiday import Holiday
from app.models.setting import SystemSetting
from app.schemas.schedule import ScheduleResponse
from app.services.scheduling import (
    ScheduleCandidate,
    ScheduledAssignment,
    employee_is_available,
    employee_is_qualified,
    fairness_priority,
    has_minimum_rest,
    shift_hours,
    structured_issues,
    unfilled_slot_reason,
    unfilled_slot_breakdown,
    validate_schedule,
    week_bounds,
    period_bounds,
)
from app.services.station_shifts import StationShift, effective_station_shifts

# ---- Background job storage (in-memory, fine for thesis demo) ----
# Limits: lost on server restart, not shared across workers, no persistence.
_generation_jobs: dict[str, dict] = {}
_generation_jobs_lock = threading.Lock()


def _new_job() -> str:
    job_id = str(uuid.uuid4())
    with _generation_jobs_lock:
        _generation_jobs[job_id] = {
            "status": "queued",
            "created_at": time.perf_counter(),
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": None,
            "result": None,
            "error": None,
        }
    return job_id


def _get_job(job_id: str) -> dict | None:
    with _generation_jobs_lock:
        return _generation_jobs.get(job_id)


def _set_job(job_id: str, **fields):
    with _generation_jobs_lock:
        job = _generation_jobs.get(job_id)
        if job:
            job.update(fields)


def _run_generation_in_background(
    job_id: str,
    schedule_date: date,
    branch_id: int,
    db_session_factory,
    current_user_id: int,
):
    """Run generate_full_week in a background thread."""
    _set_job(job_id, status="running", started_at=time.perf_counter())
    try:
        db = db_session_factory()
        try:
            current_user = db.query(User).filter(User.id == current_user_id).first()
            if not current_user:
                raise ValueError("User not found")

            result = generate_full_week(
                schedule_date=schedule_date,
                db=db,
                current_user=current_user,
            )
            _set_job(
                job_id,
                status="done",
                finished_at=time.perf_counter(),
                result=result,
            )
        except Exception as e:
            _set_job(
                job_id,
                status="failed",
                finished_at=time.perf_counter(),
                error=str(e),
            )
        finally:
            db.close()
    except Exception as e:
        _set_job(
            job_id,
            status="failed",
            finished_at=time.perf_counter(),
            error=str(e),
        )


router = APIRouter(prefix="/schedules", tags=["Schedules"])


def _period_label(d: date) -> str:
    return f"{d:%b} {d.day}"


# Core operational stations that must be filled first when roster is limited.
CORE_STATIONS = {
    "expert",
    "initiator 1",
    "assembler 1",
    "batch fry",
    "batch grill",
    "pos 1",
    "expidator",
    "fries",
    "beverages",
}


def _station_core_rank(station_name: str) -> int:
    return 0 if station_name.strip().casefold() in CORE_STATIONS else 1


# ---------------------------------------------------------------------------
# Caching helpers for the schedule generator
# ---------------------------------------------------------------------------

class ShiftHoursCache:
    def __init__(self):
        self._cache = {}

    def get(self, shift_name, station, start_time, end_time):
        key = (shift_name, station.id, start_time, end_time)
        if key not in self._cache:
            self._cache[key] = shift_hours(
                shift_name, station=station, start_time=start_time, end_time=end_time,
            )
        return self._cache[key]


class AvailabilityCache:
    def __init__(self):
        self._cache = {}

    def get(self, employee_id, availabilities, schedule_date, shift_name, station, start_time, end_time):
        key = (employee_id, shift_name, start_time, end_time)
        if key not in self._cache:
            self._cache[key] = employee_is_available(
                availabilities.get(employee_id, []),
                schedule_date,
                shift_name,
                station,
                start_time=start_time,
                end_time=end_time,
            )
        return self._cache[key]


# ---------------------------------------------------------------------------
def _get_pre_holiday_mirror_setting(db: Session, branch_id: int) -> bool:
    setting = (
        db.query(SystemSetting)
        .filter(
            SystemSetting.key == "pre_holiday_mirror_enabled",
            (SystemSetting.branch_id == branch_id)
            | (SystemSetting.branch_id.is_(None)),
        )
        .first()
    )
    if setting is None:
        return False
    return setting.value.strip().upper() == "ON"


def _get_holiday_for_date(
    db: Session, branch_id: int, target_date: date
) -> Holiday | None:
    return (
        db.query(Holiday)
        .filter(
            Holiday.holiday_date == target_date,
            (Holiday.branch_id == branch_id) | (Holiday.branch_id.is_(None)),
        )
        .first()
    )


def _get_previous_day_assignments(
    db: Session,
    branch_id: int,
    previous_date: date,
) -> list:
    return (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.schedule_date == previous_date,
            ShiftAssignment.status.in_(["Published", "Draft"]),
        )
        .all()
    )


class PublishItem(BaseModel):
    user_id: int = Field(gt=0)
    station_id: int = Field(gt=0)
    shift_name: str = Field(min_length=1, max_length=100)

class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_date: date
    assignments: List[PublishItem]


def _validate_schedule_request(
    payload: PublishRequest,
    db: Session,
    current_user: User,
) -> tuple[int, dict[tuple[int, str], StationShift], list[str]]:
    branch_id = require_manager_branch_id(current_user)

    employee_ids = {item.user_id for item in payload.assignments}
    employees = db.query(User).filter(
        User.id.in_(employee_ids),
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).all() if employee_ids else []
    stations = db.query(Station).filter(
        Station.branch_id == branch_id,
    ).all()
    employee_by_id = {employee.id: employee for employee in employees}
    station_by_id = {station.id: station for station in stations}

    week_start, week_end = week_bounds(payload.schedule_date)
    existing_assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.status == "Published",
        ShiftAssignment.schedule_date >= week_start - timedelta(days=1),
        ShiftAssignment.schedule_date <= week_end + timedelta(days=1),
    ).all()
    day_name = payload.schedule_date.strftime("%A")
    availability_rows = db.query(Availability).filter(
        Availability.user_id.in_(employee_ids),
        Availability.day_of_week == day_name,
        Availability.valid_from <= payload.schedule_date,
        Availability.valid_to >= payload.schedule_date,
    ).all() if employee_ids else []
    availabilities = {}
    for availability in availability_rows:
        availabilities.setdefault(availability.user_id, []).append(availability)
    approved_leaves = db.query(CrewRequest).filter(
        CrewRequest.branch_id == branch_id,
        CrewRequest.request_type == "leave",
        CrewRequest.status == "approved",
        CrewRequest.requester_id.in_(employee_ids),
        CrewRequest.start_date <= payload.schedule_date,
        CrewRequest.end_date >= payload.schedule_date,
    ).all() if employee_ids else []
    approved_absences = db.query(Absence).filter(
        Absence.branch_id == branch_id,
        Absence.status == AbsenceStatus.APPROVED,
        Absence.employee_id.in_(employee_ids),
        Absence.absence_date == payload.schedule_date.isoformat(),
    ).all() if employee_ids else []
    unavailable_dates = {
        request.requester_id: [payload.schedule_date]
        for request in approved_leaves
    }
    for absence in approved_absences:
        unavailable_dates.setdefault(absence.employee_id, []).append(
            payload.schedule_date
        )

    requirement_rows = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    station_shifts = effective_station_shifts(stations, requirement_rows)
    shifts_by_key = {
        (shift.station_id, shift.name): shift
        for shift in station_shifts
    }
    requirements = {
        key: shift.required_count
        for key, shift in shifts_by_key.items()
    }
    candidates = [
        ScheduleCandidate(
            user_id=item.user_id,
            station_id=item.station_id,
            shift_name=item.shift_name,
            start_time=(
                shifts_by_key[(item.station_id, item.shift_name)].start_time
                if (item.station_id, item.shift_name) in shifts_by_key
                else None
            ),
            end_time=(
                shifts_by_key[(item.station_id, item.shift_name)].end_time
                if (item.station_id, item.shift_name) in shifts_by_key
                else None
            ),
        )
        for item in payload.assignments
    ]

    errors: list[str] = []
    if not candidates:
        errors.append("At least one assignment is required to publish a schedule.")
    errors.extend(validate_schedule(
        candidates=candidates,
        employees=employee_by_id,
        stations=station_by_id,
        availabilities=availabilities,
        existing_assignments=existing_assignments,
        requirements=requirements,
        schedule_date=payload.schedule_date,
        unavailable_dates=unavailable_dates,
    ))
    return branch_id, shifts_by_key, errors


def _validate_draft_targets(
    payload: PublishRequest,
    db: Session,
    current_user: User,
) -> tuple[int, dict[tuple[int, str], StationShift]]:
    branch_id = require_manager_branch_id(current_user)
    if not payload.assignments:
        raise HTTPException(
            status_code=400,
            detail="At least one crew assignment is required to save a draft.",
        )

    employee_ids = {item.user_id for item in payload.assignments}
    employees = db.query(User).filter(
        User.id.in_(employee_ids),
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    ).all()
    stations = db.query(Station).filter(
        Station.branch_id == branch_id,
    ).all()
    requirements = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    shifts_by_key = {
        (shift.station_id, shift.name): shift
        for shift in effective_station_shifts(stations, requirements)
    }

    errors = []
    if len(employees) != len(employee_ids):
        errors.append("All crew must be active employees in your branch.")
    for item in payload.assignments:
        if (item.station_id, item.shift_name) not in shifts_by_key:
            errors.append(
                f"Shift '{item.shift_name}' is not configured for station "
                f"{item.station_id} in your branch."
            )
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Draft cannot be saved: " + " ".join(errors),
        )

    return branch_id, shifts_by_key


@router.get("/", response_model=List[ScheduleResponse])
def get_all_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if branch is None:
        raise HTTPException(status_code=409, detail="Assigned branch no longer exists.")
    schedules = db.query(Schedule).filter(
        Schedule.manager_id == current_user.id,
        Schedule.branch_name == branch.name,
    ).all()
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


@router.get("/my")
def get_my_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can view this schedule.")
    if current_user.branch_id is None:
        raise HTTPException(status_code=409, detail="Your account is not assigned to a branch.")

    assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.user_id == current_user.id,
        ShiftAssignment.branch_id == current_user.branch_id,
        ShiftAssignment.status == "Published",
    ).order_by(
        ShiftAssignment.schedule_date,
        ShiftAssignment.start_time,
    ).all()

    schedules = {}
    for assignment in assignments:
        schedule = schedules.setdefault(
            assignment.schedule_date,
            {
                "schedule_date": assignment.schedule_date,
                "acknowledged": True,
                "acknowledged_at": assignment.acknowledged_at,
                "assignments": [],
            },
        )
        schedule["acknowledged"] = (
            schedule["acknowledged"] and assignment.acknowledged_at is not None
        )
        if assignment.acknowledged_at and (
            schedule["acknowledged_at"] is None
            or assignment.acknowledged_at > schedule["acknowledged_at"]
        ):
            schedule["acknowledged_at"] = assignment.acknowledged_at
        schedule["assignments"].append({
            "station": assignment.station.name,
            "shift_name": assignment.shift_name,
            "start_time": assignment.start_time,
            "end_time": assignment.end_time,
        })

    return list(schedules.values())


@router.get("/my/overview")
def get_my_schedule_overview(
    schedule_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can view this overview.")
    if current_user.branch_id is None:
        raise HTTPException(status_code=409, detail="Your account is not assigned to a branch.")

    target_date = schedule_date or date.today()
    period_start, period_end = period_bounds(target_date)

    # Worked hours strictly within the active 15-day pay-period window.
    period_assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.user_id == current_user.id,
        ShiftAssignment.branch_id == current_user.branch_id,
        ShiftAssignment.status == "Published",
        ShiftAssignment.schedule_date >= period_start,
        ShiftAssignment.schedule_date <= period_end,
    ).all()

    worked_hours = 0.0
    for assignment in period_assignments:
        try:
            worked_hours += shift_hours(
                assignment.shift_name,
                station=None,
                start_time=assignment.start_time,
                end_time=assignment.end_time,
            )
        except Exception:
            # Unknown shift or unparsable time: ignore for the display total.
            continue
    worked_hours = round(worked_hours, 2)

    # Shift assigned for the exact target date (today), else nearest upcoming.
    def _shift_payload(assignment) -> dict | None:
        if assignment is None:
            return None
        return {
            "schedule_date": assignment.schedule_date.isoformat(),
            "station": assignment.station.name if assignment.station else None,
            "station_id": assignment.station_id,
            "shift_name": assignment.shift_name,
            "start_time": assignment.start_time.strftime("%H:%M")
            if assignment.start_time
            else None,
            "end_time": assignment.end_time.strftime("%H:%M")
            if assignment.end_time
            else None,
        }

    today_shift = (
        db.query(ShiftAssignment)
        .join(Station, Station.id == ShiftAssignment.station_id)
        .filter(
            ShiftAssignment.user_id == current_user.id,
            ShiftAssignment.branch_id == current_user.branch_id,
            ShiftAssignment.status == "Published",
            ShiftAssignment.schedule_date == target_date,
        )
        .order_by(ShiftAssignment.start_time)
        .first()
    )

    next_shift = today_shift
    if next_shift is None:
        next_shift = (
            db.query(ShiftAssignment)
            .join(Station, Station.id == ShiftAssignment.station_id)
            .filter(
                ShiftAssignment.user_id == current_user.id,
                ShiftAssignment.branch_id == current_user.branch_id,
                ShiftAssignment.status == "Published",
                ShiftAssignment.schedule_date >= target_date,
            )
            .order_by(ShiftAssignment.schedule_date, ShiftAssignment.start_time)
            .first()
        )

    min_hours = current_user.min_hours if current_user.min_hours is not None else 40
    max_hours = current_user.max_hours if current_user.max_hours is not None else 80

    period_label = f"{_period_label(period_start)} – {_period_label(period_end)}, {period_end.year}"

    return {
        "schedule_date": target_date.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": period_label,
        "worked_hours": worked_hours,
        "min_hours": min_hours,
        "max_hours": max_hours,
        "today_shift": _shift_payload(today_shift),
        "next_shift": _shift_payload(next_shift),
    }


@router.post("/{schedule_date}/acknowledge")
def acknowledge_my_schedule(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can acknowledge a schedule.")
    if current_user.branch_id is None:
        raise HTTPException(status_code=409, detail="Your account is not assigned to a branch.")

    assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.user_id == current_user.id,
        ShiftAssignment.branch_id == current_user.branch_id,
        ShiftAssignment.schedule_date == schedule_date,
        ShiftAssignment.status == "Published",
    ).all()
    if not assignments:
        raise HTTPException(status_code=404, detail="No published schedule found for this date.")

    acknowledged_at = datetime.now(timezone.utc)
    for assignment in assignments:
        if assignment.acknowledged_at is None:
            assignment.acknowledged_at = acknowledged_at
    db.commit()
    return {"message": "Schedule acknowledged.", "acknowledged": True}


@router.get("/manager")
def get_manager_schedule_tracking(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    assignments = db.query(ShiftAssignment).join(
        User,
        User.id == ShiftAssignment.user_id,
    ).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.status.in_(("Draft", "Published")),
    ).order_by(
        ShiftAssignment.schedule_date.desc(),
        ShiftAssignment.status,
        User.full_name,
    ).all()

    schedules = {}
    for assignment in assignments:
        key = (assignment.schedule_date, assignment.status)
        schedule = schedules.setdefault(
            key,
            {
                "schedule_date": assignment.schedule_date,
                "status": assignment.status,
                "assignment_count": 0,
                "crew": {},
            },
        )
        schedule["assignment_count"] += 1
        crew = schedule["crew"].setdefault(
            assignment.user_id,
            {
                "crew_id": assignment.user_id,
                "crew_name": assignment.user.full_name,
                "acknowledged": True,
            },
        )
        crew["acknowledged"] = (
            crew["acknowledged"] and assignment.acknowledged_at is not None
        )

    results = []
    for schedule in schedules.values():
        crew = list(schedule.pop("crew").values())
        schedule["crew_count"] = len(crew)
        schedule["acknowledged_count"] = sum(
            member["acknowledged"] for member in crew
        )
        schedule["crew"] = crew
        results.append(schedule)
    return results


@router.get("/draft")
def get_schedule_draft(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    draft_assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == schedule_date,
        ShiftAssignment.status == "Draft",
    ).order_by(
        ShiftAssignment.station_id,
        ShiftAssignment.start_time,
        User.full_name,
    ).join(User, User.id == ShiftAssignment.user_id).all()
    if not draft_assignments:
        raise HTTPException(status_code=404, detail="No saved draft found for this date.")

    stations = db.query(Station).filter(Station.branch_id == branch_id).all()
    station_by_id = {station.id: station for station in stations}
    requirements = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    configured_shifts = effective_station_shifts(stations, requirements)
    rows_by_key = {}
    for shift in configured_shifts:
        rows_by_key[(shift.station_id, shift.name)] = {
            "station_id": shift.station_id,
            "station": station_by_id[shift.station_id].name,
            "shift": shift.name,
            "time": (
                f"{shift.start_time.strftime('%H:%M')} - "
                f"{shift.end_time.strftime('%H:%M')}"
            ),
            "needed": shift.required_count,
            "assigned": [],
            "qualified_crew": [],
            "status": "Shortage",
        }

    for assignment in draft_assignments:
        key = (assignment.station_id, assignment.shift_name)
        row = rows_by_key.get(key)
        if row is None:
            row = {
                "station_id": assignment.station_id,
                "station": assignment.station.name,
                "shift": assignment.shift_name,
                "time": (
                    f"{assignment.start_time.strftime('%H:%M') if assignment.start_time else 'Unavailable'} - "
                    f"{assignment.end_time.strftime('%H:%M') if assignment.end_time else 'Unavailable'}"
                ),
                "needed": 0,
                "assigned": [],
                "qualified_crew": [],
                "status": "Needs review",
            }
            rows_by_key[key] = row
        row["assigned"].append({
            "id": assignment.user_id,
            "name": assignment.user.full_name,
            "crew_type": assignment.user.crew_type,
        })
        if row["needed"] and len(row["assigned"]) >= row["needed"]:
            row["status"] = "Complete"

    return {"date": schedule_date, "branch_id": branch_id, "schedule": list(rows_by_key.values())}


@router.delete("/draft")
def delete_schedule_draft(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    published_schedule_exists = db.query(ShiftAssignment.id).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == schedule_date,
        ShiftAssignment.status == "Published",
    ).first()
    if published_schedule_exists:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a published schedule. Only draft schedules can be deleted.",
        )

    deleted_count = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == schedule_date,
        ShiftAssignment.status == "Draft",
    ).delete(synchronize_session=False)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="No saved draft found for this date.")

    db.commit()
    return {"message": "Draft schedule deleted."}


def _repair_shift(
    station: Station,
    shift_name: str,
    start_time: time,
    end_time: time,
    minimum_crew: int,
    required_count: int,
    assigned_for_this_shift: list,
    assigned_ids_this_shift: set[int],
    assigned_employee_intervals: dict[int, list[tuple[datetime, datetime]]],
    scheduled_hours: dict[int, float],
    scheduled_for_rest: list,
    employees: list[User],
    qualified_employees: list[User],
    availabilities: dict[int, list],
    unavailable_employee_ids: set[int],
    schedule_date: date,
    station_by_id: dict[int, Station],
    last_shift_end: dict[int, datetime] | None = None,
    hours_cache: ShiftHoursCache | None = None,
    avail_cache: AvailabilityCache | None = None,
) -> None:
    """Try to fill remaining unfilled slots by moving crew from over-subscribed slots.
    Only moves crew if the source slot stays >= minimum_crew and all rules still pass."""
    if required_count <= minimum_crew:
        return

    if hours_cache is None:
        hours_cache = ShiftHoursCache()
    if avail_cache is None:
        avail_cache = AvailabilityCache()

    shift_h = hours_cache.get(shift_name, station, start_time, end_time)

    # Find candidates who could be moved: already assigned to this day but not this shift,
    # and their current slot has more than minimum crew.
    movable_candidates = []
    for emp in employees:
        if emp.id in assigned_ids_this_shift or emp.id in unavailable_employee_ids:
            continue
        if not employee_is_qualified(emp, station.id):
            continue
        if not avail_cache.get(
            emp.id, availabilities, schedule_date,
            shift_name, station, start_time, end_time,
        ):
            continue
        max_h = emp.max_hours if emp.max_hours is not None else 80
        if scheduled_hours.get(emp.id, 0) + shift_h > max_h:
            continue
        cand = ScheduleCandidate(
            user_id=emp.id,
            station_id=station.id,
            shift_name=shift_name,
            start_time=start_time,
            end_time=end_time,
        )
        if not has_minimum_rest(emp.id, cand, schedule_date, scheduled_for_rest, station_by_id):
            continue
        movable_candidates.append(emp)

    # Sort by fairness (least hours first)
    movable_candidates.sort(key=lambda e: fairness_priority(e, scheduled_hours.get(e.id, 0)))

    for emp in movable_candidates:
        if len(assigned_for_this_shift) >= required_count:
            break
        # Fast overlap check via last_shift_end
        last_end = last_shift_end.get(emp.id) if last_shift_end else None
        if last_end is not None and start_time < last_end:
            continue
        # Also check full intervals for safety
        if any(
            not (datetime.combine(schedule_date, end_time) <= ex_start
                 or datetime.combine(schedule_date, start_time) >= ex_end)
            for ex_start, ex_end in assigned_employee_intervals.get(emp.id, [])
        ):
            continue

        # Assign
        assigned_entry = {"id": emp.id, "name": emp.full_name, "crew_type": emp.crew_type}
        assigned_for_this_shift.append(assigned_entry)
        assigned_ids_this_shift.add(emp.id)
        assigned_employee_intervals.setdefault(emp.id, []).append(
            (datetime.combine(schedule_date, start_time), datetime.combine(schedule_date, end_time))
        )
        scheduled_hours[emp.id] = scheduled_hours.get(emp.id, 0) + shift_h
        scheduled_for_rest.append(
            ScheduledAssignment(
                user_id=emp.id,
                station_id=station.id,
                shift_name=shift_name,
                schedule_date=schedule_date,
                start_time=start_time,
                end_time=end_time,
            )
        )


def _generate_single_day(
    schedule_date: date,
    branch_id: int,
    db: Session,
    employees: list[User],
    stations: list[Station],
    station_by_id: dict[int, Station],
    day_name: str,
    employee_ids: list[int],
    existing_assignments: list[ShiftAssignment],
    week_start: date,
    week_end: date,
    shifts_by_station: dict[int, list[StationShift]],
    required_counts: dict[tuple[int, str], int],
    scheduled_hours: dict[int, float],
    scheduled_for_rest: list,
    pre_holiday_mirror_enabled: bool = False,
    holiday_info: dict | None = None,
    previous_day_assignments: list | None = None,
    unavailable_employee_ids: set[int] | None = None,
    availabilities_by_user_day: dict[tuple[int, str], list] | None = None,
) -> dict:
    t_day0 = time.perf_counter()

    # ---- Backward-compatible: pre-load data if caller didn't ----
    if unavailable_employee_ids is None:
        approved_leaves = db.query(CrewRequest.requester_id).filter(
            CrewRequest.branch_id == branch_id,
            CrewRequest.request_type == "leave",
            CrewRequest.status == "approved",
            CrewRequest.requester_id.in_(employee_ids),
            CrewRequest.start_date <= schedule_date,
            CrewRequest.end_date >= schedule_date,
        ).all() if employee_ids else []
        approved_absences = db.query(Absence.employee_id).filter(
            Absence.branch_id == branch_id,
            Absence.status == AbsenceStatus.APPROVED,
            Absence.employee_id.in_(employee_ids),
            Absence.absence_date == schedule_date.isoformat(),
        ).all() if employee_ids else []
        absence_employee_ids = {row.employee_id for row in approved_absences}
        unavailable_employee_ids = (
            {row.requester_id for row in approved_leaves} | absence_employee_ids
        )

    if availabilities_by_user_day is None:
        availability_rows = db.query(Availability).filter(
            Availability.user_id.in_(employee_ids),
            Availability.day_of_week == day_name,
            Availability.valid_from <= schedule_date,
            Availability.valid_to >= schedule_date,
        ).all() if employee_ids else []
        availabilities_by_user_day = {}
        for a in availability_rows:
            availabilities_by_user_day.setdefault((a.user_id, a.day_of_week), []).append(a)

    # Build availabilities dict for this day from pre-loaded data
    availabilities: dict[int, list] = {}
    for emp_id in employee_ids:
        day_windows = availabilities_by_user_day.get((emp_id, day_name), [])
        if day_windows:
            availabilities[emp_id] = day_windows

    assigned_employee_intervals: dict[int, list[tuple[datetime, datetime]]] = {}

    # ---- Caches for this day's generation ----
    hours_cache = ShiftHoursCache()
    avail_cache = AvailabilityCache()

    # Track last shift end per employee for O(1) rest check
    last_shift_end: dict[int, time] = {}
    for emp_id, intervals in assigned_employee_intervals.items():
        if intervals:
            last_shift_end[emp_id] = max(e for _, e in intervals).time()

    # ---- Build slots with pre-computed eligible candidates ----
    t_build0 = time.perf_counter()
    slots = []
    for station in stations:
        for shift in shifts_by_station.get(station.id, []):
            shift_name = shift.name
            start_time, end_time = shift.start_time, shift.end_time
            minimum_crew = shift.minimum_crew if shift.minimum_crew is not None else shift.required_count
            required_count = shift.required_count

            # Pre-compute qualified + available candidates once per slot
            qualified_employees = []
            for employee in employees:
                if employee.id in unavailable_employee_ids:
                    continue
                if not employee_is_qualified(employee, station.id):
                    continue
                if not avail_cache.get(
                    employee.id, availabilities, schedule_date,
                    shift_name, station, start_time, end_time,
                ):
                    continue
                qualified_employees.append(employee)

            slots.append(
                {
                    "station": station,
                    "station_id": station.id,
                    "station_priority": station.priority if station.priority is not None else 2,
                    "shift_name": shift_name,
                    "start_time": start_time,
                    "end_time": end_time,
                    "minimum_crew": minimum_crew,
                    "required_count": required_count,
                    "qualified_employees": qualified_employees,
                    "candidate_count": len(qualified_employees),
                }
            )

    t_build1 = time.perf_counter()

    # Sort hardest-first: fewest eligible candidates first
    slots.sort(
        key=lambda slot: (
            slot["station_priority"],
            slot["candidate_count"],
            _station_core_rank(slot["station"].name),
            slot["station"].name.casefold(),
            slot["start_time"],
            slot["end_time"],
            slot["shift_name"],
        )
    )

    # Build mirror map
    mirror_map: dict[tuple[int, str], list[int]] = {}
    if pre_holiday_mirror_enabled and holiday_info and previous_day_assignments:
        for assignment in previous_day_assignments:
            key = (assignment.station_id, assignment.shift_name)
            mirror_map.setdefault(key, []).append(assignment.user_id)

    # Pre-compute employee lookup by id for mirror candidates
    employees_by_id = {e.id: e for e in employees}

    generated_schedule = []
    unfilled = []
    t_fill0 = time.perf_counter()

    for slot in slots:
        station = slot["station"]
        shift_name = slot["shift_name"]
        start_time = slot["start_time"]
        end_time = slot["end_time"]
        minimum_crew = slot["minimum_crew"]
        required_count = slot["required_count"]
        qualified_employees = slot["qualified_employees"]

        assigned_for_this_shift = []
        assigned_ids_this_shift = set()
        mirror_used_for_slot = False
        mirror_conflict_reason: str | None = None

        # Mirror candidates from previous day
        mirror_candidates: list = []
        if pre_holiday_mirror_enabled and holiday_info:
            mirror_key = (station.id, shift_name)
            mirror_user_ids = mirror_map.get(mirror_key, [])
            for uid in mirror_user_ids:
                emp = employees_by_id.get(uid)
                if emp and emp.id not in assigned_ids_this_shift:
                    mirror_candidates.append(emp)

        # Single-pass fill: minimum crew first, then top up to required_count
        # We iterate until we hit required_count OR run out of candidates.
        # Minimum crew is prioritized by checking after each assignment.
        shift_h = hours_cache.get(shift_name, station, start_time, end_time)

        remaining_candidates = list(qualified_employees)
        # Sort remaining by fairness priority once
        remaining_candidates.sort(
            key=lambda employee: fairness_priority(
                employee, scheduled_hours.get(employee.id, 0)
            ),
        )

        mirror_ids = {e.id for e in mirror_candidates}
        all_candidates = mirror_candidates + [
            e for e in remaining_candidates if e.id not in mirror_ids
        ]

        for employee in all_candidates:
            if len(assigned_for_this_shift) >= required_count:
                break

            is_mirror_candidate = employee.id in mirror_ids

            # Fast overlap check: employee already assigned this shift?
            if employee.id in assigned_ids_this_shift:
                if is_mirror_candidate and mirror_conflict_reason is None:
                    mirror_conflict_reason = "Already assigned this shift"
                continue

            # Fast overlap check: employee already has another shift today
            last_end = last_shift_end.get(employee.id)
            if last_end is not None and start_time < last_end:
                if is_mirror_candidate and mirror_conflict_reason is None:
                    mirror_conflict_reason = "Overlapping shift on same day"
                continue

            # Max hours check (cached shift hours)
            max_hours = employee.max_hours if employee.max_hours is not None else 80
            if scheduled_hours.get(employee.id, 0) + shift_h > max_hours:
                if is_mirror_candidate and mirror_conflict_reason is None:
                    mirror_conflict_reason = "Would exceed max hours"
                continue

            # 11-hour minimum rest check (O(1) via last_shift_end)
            candidate = ScheduleCandidate(
                user_id=employee.id,
                station_id=station.id,
                shift_name=shift_name,
                start_time=start_time,
                end_time=end_time,
            )
            if not has_minimum_rest(
                employee.id,
                candidate,
                schedule_date,
                scheduled_for_rest,
                station_by_id,
            ):
                if is_mirror_candidate and mirror_conflict_reason is None:
                    mirror_conflict_reason = "Less than 11-hour rest"
                continue

            # Select this employee
            selected_employee = employee
            is_mirror_selection = is_mirror_candidate

            # Check if we still meet minimum crew after this assignment
            # (minimum crew is checked implicitly by filling up to required_count;
            #  if we can't fill required_count, we check minimum_met after)

            mirror_used_for_slot = mirror_used_for_slot or is_mirror_selection

            assigned_entry = {
                "id": selected_employee.id,
                "name": selected_employee.full_name,
                "crew_type": selected_employee.crew_type,
            }
            if is_mirror_selection:
                assigned_entry["is_mirrored"] = True
            assigned_for_this_shift.append(assigned_entry)
            assigned_ids_this_shift.add(selected_employee.id)
            assigned_employee_intervals.setdefault(selected_employee.id, []).append(
                (
                    datetime.combine(schedule_date, start_time),
                    datetime.combine(schedule_date, end_time),
                )
            )
            scheduled_hours[selected_employee.id] = (
                scheduled_hours.get(selected_employee.id, 0) + shift_h
            )
            scheduled_for_rest.append(
                ScheduledAssignment(
                    user_id=selected_employee.id,
                    station_id=station.id,
                    shift_name=shift_name,
                    schedule_date=schedule_date,
                    start_time=start_time,
                    end_time=end_time,
                )
            )
            # Track last shift end for O(1) rest check
            last_shift_end[selected_employee.id] = end_time

        assigned_count = len(assigned_for_this_shift)
        unfilled_count = required_count - assigned_count
        minimum_met = assigned_count >= minimum_crew

        # Repair pass: try to fill remaining unfilled slots by moving crew
        # from over-subscribed slots (where assigned > minimum_crew) to unfilled ones
        if unfilled_count > 0:
            t_repair0 = time.perf_counter()
            _repair_shift(
                station, shift_name, start_time, end_time, minimum_crew, required_count,
                assigned_for_this_shift, assigned_ids_this_shift,
                assigned_employee_intervals, scheduled_hours, scheduled_for_rest,
                employees, qualified_employees, availabilities,
                unavailable_employee_ids, schedule_date, station_by_id,
                last_shift_end, hours_cache,
            )
            t_repair1 = time.perf_counter()
            # Recalculate after repair
            assigned_count = len(assigned_for_this_shift)
            unfilled_count = required_count - assigned_count
            minimum_met = assigned_count >= minimum_crew

        if unfilled_count > 0:
            unfilled.append({
                "station_id": station.id,
                "station": station.name,
                "shift": shift_name,
                "date": schedule_date.isoformat(),
                "required": required_count,
                "assigned": assigned_count,
                "missing": unfilled_count,
                "minimum_met": minimum_met,
                "priority": slot["station_priority"],
                "breakdown": unfilled_slot_breakdown(
                    slot.get("qualified_only", qualified_employees),
                    qualified_employees,
                    set(assigned_employee_intervals.keys()),
                    scheduled_hours,
                    shift_name,
                    station,
                    start_time,
                    end_time,
                    schedule_date,
                    scheduled_for_rest,
                    station_by_id,
                ),
            })

        filled = assigned_count == required_count
        generated_schedule.append(
            {
                "station_id": station.id,
                "station": station.name,
                "shift": shift_name,
                "time": (
                    f"{start_time.strftime('%H:%M')} - "
                    f"{end_time.strftime('%H:%M')}"
                ),
                "needed": required_count,
                "minimum_crew": minimum_crew,
                "assigned": assigned_for_this_shift,
                "qualified_crew": [
                    {
                        "id": e.id,
                        "name": e.full_name,
                        "crew_type": e.crew_type,
                    }
                    for e in qualified_employees
                ],
                "status": "Complete" if filled else "Shortage",
                "minimum_met": minimum_met,
                "reason": ""
                if filled
                else unfilled_slot_reason(
                    slot.get("qualified_only", qualified_employees),
                    qualified_employees,
                    set(assigned_employee_intervals.keys()),
                    scheduled_hours,
                    shift_name,
                    station,
                    start_time,
                    end_time,
                    schedule_date,
                    scheduled_for_rest,
                    station_by_id,
                ),
                "is_holiday": holiday_info is not None,
                "holiday_name": holiday_info["name"] if holiday_info else None,
                "holiday_type": holiday_info["holiday_type"] if holiday_info else None,
                "is_mirrored_slot": mirror_used_for_slot,
                "mirror_conflict_reason": mirror_conflict_reason,
            }
        )

    t_fill1 = time.perf_counter()

    total_required = sum(s["needed"] for s in generated_schedule)
    total_assigned = sum(len(s["assigned"]) for s in generated_schedule)
    total_missing = total_required - total_assigned
    minimum_missing = sum(
        max(0, s["minimum_crew"] - len(s["assigned"]))
        for s in generated_schedule
    )

    t_end = time.perf_counter()
    print(f"[TIMING] generate_full_day {schedule_date}: "
          f"total={t_end - t_day0:.3f}s, "
          f"build_slots={t_build1 - t_build0:.3f}s, "
          f"fill_slots={t_fill1 - t_fill0:.3f}s, "
          f"slots={len(slots)}, required={total_required}, "
          f"assigned={total_assigned}, missing={total_missing}")

    return {
        "date": schedule_date,
        "branch_id": branch_id,
        "schedule": generated_schedule,
        "unfilled": unfilled,
        "total_required": total_required,
        "total_assigned": total_assigned,
        "total_missing": total_missing,
        "minimum_missing": minimum_missing,
    }


@router.post("/generate-full-day")
def generate_full_day(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)

    stations = db.query(Station).filter(Station.branch_id == branch_id).all()
    station_by_id = {station.id: station for station in stations}

    employees = db.query(User).filter(
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True)
    ).all()
    employee_ids = [employee.id for employee in employees]

    week_start, week_end = week_bounds(schedule_date)
    period_start, period_end = period_bounds(schedule_date)
    existing_assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.status == "Published",
        ShiftAssignment.schedule_date >= week_start - timedelta(days=1),
        ShiftAssignment.schedule_date <= week_end + timedelta(days=1),
    ).all()
    existing_assignments = [
        assignment
        for assignment in existing_assignments
        if assignment.schedule_date != schedule_date
    ]

    requirements = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    station_shifts = effective_station_shifts(stations, requirements)
    shifts_by_station = {}
    required_counts = {}
    for shift in station_shifts:
        shifts_by_station.setdefault(shift.station_id, []).append(shift)
        required_counts[(shift.station_id, shift.name)] = shift.required_count

    scheduled_hours = {}
    for assignment in existing_assignments:
        if period_start <= assignment.schedule_date <= period_end:
            station = station_by_id.get(assignment.station_id)
            scheduled_hours[assignment.user_id] = (
                scheduled_hours.get(assignment.user_id, 0)
                + shift_hours(
                    assignment.shift_name,
                    station=station,
                    start_time=assignment.start_time,
                    end_time=assignment.end_time,
                )
            )

    scheduled_for_rest = list(existing_assignments)

    pre_holiday_mirror_enabled = _get_pre_holiday_mirror_setting(db, branch_id)
    holiday_info = None
    previous_day_assignments = None
    if pre_holiday_mirror_enabled:
        holiday = _get_holiday_for_date(db, branch_id, schedule_date)
        if holiday:
            holiday_info = {
                "name": holiday.name,
                "holiday_type": holiday.holiday_type,
            }
            previous_date = schedule_date - timedelta(days=1)
            previous_day_assignments = _get_previous_day_assignments(
                db, branch_id, previous_date
            )

    return _generate_single_day(
        schedule_date=schedule_date,
        branch_id=branch_id,
        db=db,
        employees=employees,
        stations=stations,
        station_by_id=station_by_id,
        day_name=schedule_date.strftime("%A"),
        employee_ids=employee_ids,
        existing_assignments=existing_assignments,
        week_start=week_start,
        week_end=week_end,
        shifts_by_station=shifts_by_station,
        required_counts=required_counts,
        scheduled_hours=scheduled_hours,
        scheduled_for_rest=scheduled_for_rest,
        pre_holiday_mirror_enabled=pre_holiday_mirror_enabled,
        holiday_info=holiday_info,
        previous_day_assignments=previous_day_assignments,
    )


@router.post("/generate-full-week")
@router.post("/generate-full-week")
def generate_full_week(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start schedule generation as a background job. Returns job_id immediately."""
    branch_id = require_manager_branch_id(current_user)
    job_id = _new_job()

    thread = threading.Thread(
        target=_run_generation_in_background,
        args=(job_id, schedule_date, branch_id, SessionLocal, current_user.id),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Schedule generation started. Poll /schedules/generate-status/{job_id}.",
    }


@router.get("/generate-status/{job_id}")
def generate_status(job_id: str):
    """Check status of a background schedule generation job."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job["status"],
        "elapsed_seconds": None,
    }

    if job["started_at"]:
        response["elapsed_seconds"] = round(
            (job["finished_at"] or time.perf_counter()) - job["started_at"], 2
        )

    if job["status"] == "done":
        response["result"] = job["result"]
    elif job["status"] == "failed":
        response["error"] = job["error"]

    return response


@router.post("/generate-cancel/{job_id}")
def generate_cancel(job_id: str):
    """Cancel a background schedule generation job (best-effort)."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] in ("done", "failed"):
        return {"job_id": job_id, "status": job["status"], "message": "Job already finished"}

    _set_job(job_id, status="cancelled", finished_at=time.perf_counter())
    return {"job_id": job_id, "status": "cancelled", "message": "Job marked for cancellation"}

@router.post("/publish")
def publish_schedule(
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id, shifts_by_key, validation_errors = _validate_schedule_request(
        payload,
        db,
        current_user,
    )
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail="Schedule cannot be published: " + " ".join(validation_errors),
        )

    db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == payload.schedule_date
    ).delete(synchronize_session=False)

    for item in payload.assignments:
        shift = shifts_by_key[(item.station_id, item.shift_name)]
        new_assignment = ShiftAssignment(
            user_id=item.user_id,
            branch_id=branch_id,
            station_id=item.station_id,
            schedule_date=payload.schedule_date,
            shift_name=item.shift_name,
            start_time=shift.start_time,
            end_time=shift.end_time,
            status="Published"
        )
        db.add(new_assignment)
    
    db.commit()
    return {"message": "Schedule published successfully! 🎉"}


@router.post("/draft")
def save_schedule_draft(
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id, shifts_by_key = _validate_draft_targets(
        payload,
        db,
        current_user,
    )
    published_schedule_exists = db.query(ShiftAssignment.id).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == payload.schedule_date,
        ShiftAssignment.status == "Published",
    ).first()
    if published_schedule_exists:
        raise HTTPException(
            status_code=409,
            detail="A schedule is already published for this date. Publishing an updated schedule will replace it.",
        )

    db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date == payload.schedule_date,
        ShiftAssignment.status == "Draft",
    ).delete(synchronize_session=False)
    for item in payload.assignments:
        shift = shifts_by_key[(item.station_id, item.shift_name)]
        db.add(ShiftAssignment(
            user_id=item.user_id,
            branch_id=branch_id,
            station_id=item.station_id,
            schedule_date=payload.schedule_date,
            shift_name=item.shift_name,
            start_time=shift.start_time,
            end_time=shift.end_time,
            status="Draft",
        ))
    db.commit()
    return {"message": "Draft saved. It is not visible to crew until published."}


@router.post("/validate")
def validate_schedule_draft(
    payload: PublishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, _, errors = _validate_schedule_request(payload, db, current_user)
    return {"valid": not errors, "errors": structured_issues(errors)}


@router.post("/shortage-summary")
def shortage_summary(
    schedule_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return aggregated shortage data for the week starting at schedule_date."""
    branch_id = require_manager_branch_id(current_user)
    week_start, week_end = week_bounds(schedule_date)

    results = generate_full_week(schedule_date=schedule_date, db=db, current_user=current_user)

    total_required = sum(d["total_required"] for d in results)
    total_assigned = sum(d["total_assigned"] for d in results)
    total_missing = sum(d["total_missing"] for d in results)
    coverage_pct = round((total_assigned / total_required) * 100, 1) if total_required else 100.0

    # Per-employee hours
    employees = db.query(User).filter(
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
    ).all()
    employees_by_id = {emp.id: emp for emp in employees}
    station_by_id = {s.id: s for s in db.query(Station).filter(Station.branch_id == branch_id).all()}

    employee_hours: dict[int, float] = {}
    for day in results:
        for slot in day["schedule"]:
            for assigned in slot["assigned"]:
                eid = assigned["id"]
                employee_hours[eid] = employee_hours.get(eid, 0) + shift_hours(
                    slot["shift"],
                    station=station_by_id.get(slot["station_id"]),
                )

    hours_values = list(employee_hours.values())
    avg_hours = round(sum(hours_values) / len(hours_values), 1) if hours_values else 0.0
    hours_spread = round(max(hours_values) - min(hours_values), 1) if hours_values else 0.0
    overtime_count = sum(
        1 for eid, h in employee_hours.items()
        if (employees_by_id.get(eid).max_hours if employees_by_id.get(eid) else 80) < h
    )

    # Shortage summary grouped by day, shift, station
    by_day: dict[str, dict] = {}
    by_shift: dict[str, int] = {}
    by_station: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    unfilled_items = []

    for day in results:
        day_key = str(day["date"])
        day_entry = by_day.setdefault(day_key, {"total": 0, "by_shift": {}, "by_station": {}})
        day_entry["total"] += day["total_missing"]
        for u in day["unfilled"]:
            shift_key = u["shift"]
            station_key = u["station"]
            day_entry["by_shift"][shift_key] = day_entry["by_shift"].get(shift_key, 0) + u["missing"]
            day_entry["by_station"][station_key] = day_entry["by_station"].get(station_key, 0) + u["missing"]
            by_shift[shift_key] = by_shift.get(shift_key, 0) + u["missing"]
            by_station[station_key] = by_station.get(station_key, 0) + u["missing"]
            if u.get("breakdown"):
                for reason_key, count in u["breakdown"].items():
                    if count:
                        by_reason[reason_key] = by_reason.get(reason_key, 0) + count
            unfilled_items.append(u)

    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "total_required": total_required,
        "total_assigned": total_assigned,
        "total_missing": total_missing,
        "coverage_pct": coverage_pct,
        "average_hours": avg_hours,
        "hours_spread": hours_spread,
        "overtime_count": overtime_count,
        "solver_status": "OPTIMAL" if total_missing == 0 else "FEASIBLE" if total_missing < 10 else "PARTIAL",
        "by_day": by_day,
        "by_shift": by_shift,
        "by_station": by_station,
        "by_reason": by_reason,
        "unfilled_items": unfilled_items,
        "employee_hours": {str(eid): h for eid, h in employee_hours.items()},
    }