from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.assignment import ShiftAssignment
from app.models.availability import Availability
from app.models.crew_request import CrewRequest
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.schemas.crew_request import (
    LeaveRequestCreate,
    ManagerDecision,
    SwapRequestCreate,
    SwapResponse,
)
from app.services.scheduling import (
    ScheduleCandidate,
    ScheduledAssignment,
    validate_schedule,
    week_bounds,
)
from app.services.station_shifts import effective_station_shifts

router = APIRouter(prefix="/requests", tags=["Crew requests"])


def _require_crew(current_user: User) -> None:
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can submit or respond to requests.")
    if current_user.branch_id is None:
        raise HTTPException(status_code=409, detail="Crew account is not assigned to a branch.")


def _assignment_summary(db: Session, assignment_id: int | None) -> dict | None:
    if assignment_id is None:
        return None
    assignment = db.query(ShiftAssignment).filter(
        ShiftAssignment.id == assignment_id,
    ).first()
    if assignment is None:
        return None
    station = db.query(Station).filter(Station.id == assignment.station_id).first()
    return {
        "id": assignment.id,
        "date": assignment.schedule_date.isoformat(),
        "shift": assignment.shift_name,
        "station": station.name if station else "Unknown station",
        "start_time": assignment.start_time.strftime("%H:%M") if assignment.start_time else None,
        "end_time": assignment.end_time.strftime("%H:%M") if assignment.end_time else None,
    }


def _request_summary(db: Session, request: CrewRequest, *, include_conflicts: bool = False) -> dict:
    requester = db.query(User).filter(User.id == request.requester_id).first()
    target = (
        db.query(User).filter(User.id == request.target_user_id).first()
        if request.target_user_id is not None
        else None
    )
    result = {
        "id": request.id,
        "request_type": request.request_type,
        "status": request.status,
        "requester_id": request.requester_id,
        "requester_name": requester.full_name if requester else "Former crew member",
        "target_user_id": request.target_user_id,
        "target_name": target.full_name if target else None,
        "start_date": request.start_date.isoformat() if request.start_date else None,
        "end_date": request.end_date.isoformat() if request.end_date else None,
        "reason": request.reason,
        "requester_shift": _assignment_summary(db, request.requester_assignment_id),
        "target_shift": _assignment_summary(db, request.target_assignment_id),
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "conflicting_assignments": 0,
    }
    if include_conflicts and request.request_type == "leave":
        result["conflicting_assignments"] = db.query(ShiftAssignment).filter(
            ShiftAssignment.user_id == request.requester_id,
            ShiftAssignment.branch_id == request.branch_id,
            ShiftAssignment.status == "Published",
            ShiftAssignment.schedule_date >= request.start_date,
            ShiftAssignment.schedule_date <= request.end_date,
        ).count()
    return result


@router.post("/leave", status_code=status.HTTP_201_CREATED)
def create_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crew(current_user)
    if payload.start_date < date.today():
        raise HTTPException(status_code=400, detail="Leave requests must start today or later.")

    overlapping_request = db.query(CrewRequest).filter(
        CrewRequest.requester_id == current_user.id,
        CrewRequest.branch_id == current_user.branch_id,
        CrewRequest.request_type == "leave",
        CrewRequest.status.in_(("pending_manager", "approved")),
        CrewRequest.start_date <= payload.end_date,
        CrewRequest.end_date >= payload.start_date,
    ).first()
    if overlapping_request:
        raise HTTPException(status_code=409, detail="You already have a pending or approved leave request for these dates.")

    request = CrewRequest(
        request_type="leave",
        status="pending_manager",
        branch_id=current_user.branch_id,
        requester_id=current_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason.strip() if payload.reason else None,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return _request_summary(db, request)


@router.get("/swap-options")
def get_swap_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crew(current_user)
    assignments = db.query(ShiftAssignment, User, Station).join(
        User, User.id == ShiftAssignment.user_id
    ).join(
        Station, Station.id == ShiftAssignment.station_id
    ).filter(
        ShiftAssignment.branch_id == current_user.branch_id,
        ShiftAssignment.status == "Published",
        ShiftAssignment.schedule_date >= date.today(),
        User.is_active.is_(True),
        User.branch_id == current_user.branch_id,
    ).order_by(
        ShiftAssignment.schedule_date,
        ShiftAssignment.start_time,
        User.full_name,
    ).all()
    own_shifts = []
    other_shifts = []
    for assignment, employee, station in assignments:
        shift = {
            "id": assignment.id,
            "user_id": employee.id,
            "crew_name": employee.full_name,
            "date": assignment.schedule_date.isoformat(),
            "shift": assignment.shift_name,
            "station": station.name,
            "start_time": assignment.start_time.strftime("%H:%M") if assignment.start_time else None,
            "end_time": assignment.end_time.strftime("%H:%M") if assignment.end_time else None,
        }
        (own_shifts if employee.id == current_user.id else other_shifts).append(shift)
    return {"my_shifts": own_shifts, "crew_shifts": other_shifts}


@router.post("/swaps", status_code=status.HTTP_201_CREATED)
def create_swap_request(
    payload: SwapRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crew(current_user)
    assignments = db.query(ShiftAssignment).filter(
        ShiftAssignment.id.in_(
            (payload.requester_assignment_id, payload.target_assignment_id)
        ),
        ShiftAssignment.branch_id == current_user.branch_id,
        ShiftAssignment.status == "Published",
    ).all()
    by_id = {assignment.id: assignment for assignment in assignments}
    requester_shift = by_id.get(payload.requester_assignment_id)
    target_shift = by_id.get(payload.target_assignment_id)
    if requester_shift is None or requester_shift.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Your published shift was not found.")
    if target_shift is None:
        raise HTTPException(status_code=404, detail="The other crew member's published shift was not found.")
    if target_shift.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Choose a shift assigned to another crew member.")
    eligible_target = db.query(User).filter(
        User.id == target_shift.user_id,
        User.branch_id == current_user.branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
    ).first()
    if eligible_target is None:
        raise HTTPException(status_code=404, detail="The other shift is not assigned to active crew in your branch.")
    if min(requester_shift.schedule_date, target_shift.schedule_date) < date.today():
        raise HTTPException(status_code=400, detail="Past shifts cannot be swapped.")

    pending = db.query(CrewRequest).filter(
        CrewRequest.request_type == "swap",
        CrewRequest.status.in_(("pending_recipient", "pending_manager")),
        or_(
            CrewRequest.requester_assignment_id.in_(
                (requester_shift.id, target_shift.id)
            ),
            CrewRequest.target_assignment_id.in_(
                (requester_shift.id, target_shift.id)
            ),
        ),
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="One of these shifts already has a pending swap request.")

    request = CrewRequest(
        request_type="swap",
        status="pending_recipient",
        branch_id=current_user.branch_id,
        requester_id=current_user.id,
        target_user_id=target_shift.user_id,
        requester_assignment_id=requester_shift.id,
        target_assignment_id=target_shift.id,
        reason=payload.reason.strip() if payload.reason else None,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return _request_summary(db, request)


@router.get("/my")
def get_my_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crew(current_user)
    requests = db.query(CrewRequest).filter(
        or_(
            CrewRequest.requester_id == current_user.id,
            CrewRequest.target_user_id == current_user.id,
        )
    ).order_by(CrewRequest.created_at.desc(), CrewRequest.id.desc()).limit(200).all()
    return [_request_summary(db, request) for request in requests]


@router.post("/{request_id}/swap-response")
def respond_to_swap(
    request_id: int,
    payload: SwapResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_crew(current_user)
    request = db.query(CrewRequest).filter(
        CrewRequest.id == request_id,
        CrewRequest.request_type == "swap",
        CrewRequest.target_user_id == current_user.id,
    ).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Swap request not found.")
    if request.status != "pending_recipient":
        raise HTTPException(status_code=409, detail="This swap request has already been answered.")
    request.status = "pending_manager" if payload.accept else "rejected"
    db.commit()
    db.refresh(request)
    return _request_summary(db, request)


@router.get("/manager")
def get_pending_manager_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    requests = db.query(CrewRequest).filter(
        CrewRequest.branch_id == branch_id,
        CrewRequest.status == "pending_manager",
    ).order_by(CrewRequest.created_at, CrewRequest.id).limit(200).all()
    return [
        _request_summary(db, request, include_conflicts=True)
        for request in requests
    ]


def _validate_swap(db: Session, request: CrewRequest, branch_id: int) -> list[str]:
    assignment_ids = (request.requester_assignment_id, request.target_assignment_id)
    assignments_by_id = {
        assignment.id: assignment
        for assignment in db.query(ShiftAssignment).filter(
            ShiftAssignment.id.in_(assignment_ids),
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.status == "Published",
        ).all()
    }
    first = assignments_by_id.get(request.requester_assignment_id)
    second = assignments_by_id.get(request.target_assignment_id)
    if first is None or second is None:
        return ["One of the published shifts no longer exists."]
    if first.user_id != request.requester_id or second.user_id != request.target_user_id:
        return ["One of the shifts has changed since the request was submitted."]

    affected_dates = sorted({first.schedule_date, second.schedule_date})
    if affected_dates[0] < date.today():
        return ["Past shifts cannot be swapped."]

    stations = db.query(Station).filter(Station.branch_id == branch_id).all()
    station_by_id = {station.id: station for station in stations}
    requirements = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    shifts = effective_station_shifts(stations, requirements)
    requirements_by_key = {
        (shift.station_id, shift.name): shift.required_count
        for shift in shifts
    }
    week_start = min(week_bounds(day)[0] for day in affected_dates)
    week_end = max(week_bounds(day)[1] for day in affected_dates)
    existing_rows = db.query(ShiftAssignment).filter(
        ShiftAssignment.branch_id == branch_id,
        ShiftAssignment.schedule_date >= week_start - timedelta(days=1),
        ShiftAssignment.schedule_date <= week_end + timedelta(days=1),
        ShiftAssignment.status == "Published",
    ).all()
    replacements = {
        first.id: second.user_id,
        second.id: first.user_id,
    }
    existing_assignments = [
        ScheduledAssignment(
            user_id=replacements.get(assignment.id, assignment.user_id),
            station_id=assignment.station_id,
            shift_name=assignment.shift_name,
            schedule_date=assignment.schedule_date,
            start_time=assignment.start_time,
            end_time=assignment.end_time,
        )
        for assignment in existing_rows
    ]

    employee_ids = {
        assignment.user_id
        for assignment in existing_assignments
    }
    employees = db.query(User).filter(
        User.id.in_(employee_ids),
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
    ).all() if employee_ids else []
    employee_by_id = {employee.id: employee for employee in employees}
    errors = []

    for schedule_date in affected_dates:
        daily_assignments = [
            assignment
            for assignment in existing_assignments
            if assignment.schedule_date == schedule_date
        ]
        candidates = [
            ScheduleCandidate(
                user_id=assignment.user_id,
                station_id=assignment.station_id,
                shift_name=assignment.shift_name,
                start_time=assignment.start_time,
                end_time=assignment.end_time,
            )
            for assignment in daily_assignments
        ]
        day_name = schedule_date.strftime("%A")
        availability_rows = db.query(Availability).filter(
            Availability.user_id.in_(employee_by_id),
            Availability.day_of_week == day_name,
            Availability.valid_from <= schedule_date,
            Availability.valid_to >= schedule_date,
        ).all() if employee_by_id else []
        availabilities = {}
        for availability in availability_rows:
            availabilities.setdefault(availability.user_id, []).append(availability)
        approved_leaves = db.query(CrewRequest.requester_id).filter(
            CrewRequest.branch_id == branch_id,
            CrewRequest.request_type == "leave",
            CrewRequest.status == "approved",
            CrewRequest.requester_id.in_(employee_by_id),
            CrewRequest.start_date <= schedule_date,
            CrewRequest.end_date >= schedule_date,
        ).all() if employee_by_id else []
        unavailable_dates = {
            row.requester_id: [schedule_date]
            for row in approved_leaves
        }
        errors.extend(validate_schedule(
            candidates=candidates,
            employees=employee_by_id,
            stations=station_by_id,
            availabilities=availabilities,
            existing_assignments=[
                assignment
                for assignment in existing_assignments
                if assignment.schedule_date != schedule_date
            ],
            requirements=requirements_by_key,
            schedule_date=schedule_date,
            unavailable_dates=unavailable_dates,
        ))
    return errors


@router.post("/{request_id}/decision")
def decide_request(
    request_id: int,
    payload: ManagerDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    request = db.query(CrewRequest).filter(
        CrewRequest.id == request_id,
        CrewRequest.branch_id == branch_id,
    ).first()
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found.")
    if request.status != "pending_manager":
        raise HTTPException(status_code=409, detail="This request is no longer awaiting manager review.")

    if (
        payload.decision == "approve"
        and request.request_type == "leave"
        and request.end_date < date.today()
    ):
        raise HTTPException(status_code=409, detail="Past leave requests can no longer be approved.")

    if payload.decision == "approve" and request.request_type == "swap":
        validation_errors = _validate_swap(db, request, branch_id)
        if validation_errors:
            raise HTTPException(
                status_code=409,
                detail="Swap cannot be approved: " + " ".join(validation_errors),
            )
        first = db.query(ShiftAssignment).filter(
            ShiftAssignment.id == request.requester_assignment_id,
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.status == "Published",
        ).with_for_update().first()
        second = db.query(ShiftAssignment).filter(
            ShiftAssignment.id == request.target_assignment_id,
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.status == "Published",
        ).with_for_update().first()
        if first is None or second is None:
            raise HTTPException(status_code=409, detail="One of the shifts no longer exists.")
        first.user_id, second.user_id = second.user_id, first.user_id

    request.status = "approved" if payload.decision == "approve" else "rejected"
    request.reviewed_by = current_user.id
    db.commit()
    db.refresh(request)
    return _request_summary(db, request)
