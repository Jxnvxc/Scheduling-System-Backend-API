from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.database import get_db
from app.models.availability import Availability
from app.models.assignment import ShiftAssignment
from app.models.requirement import StaffingRequirement
from app.models.user import User, UserRole
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/manager")
def get_manager_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view manager statistics",
    )

    today = date.today()
    today_name = today.strftime("%A")

    base_crew = db.query(User).filter(
        User.role == UserRole.EMPLOYEE,
        User.branch_id == branch_id,
        User.is_active.is_(True),
    )

    team_members = base_crew.count()

    todays_staff = (
        base_crew.join(Availability, Availability.user_id == User.id)
        .filter(
            Availability.day_of_week == today_name,
            Availability.valid_from <= today,
            Availability.valid_to >= today,
        )
        .distinct()
        .count()
    )

    requirements = (
        db.query(StaffingRequirement)
        .filter(
            StaffingRequirement.branch_id == branch_id,
            StaffingRequirement.enabled.is_(True),
        )
        .all()
    )

    total_required = 0
    total_assigned = 0
    for req in requirements:
        total_required += req.required_count
        assigned_today = (
            db.query(ShiftAssignment)
            .filter(
                ShiftAssignment.branch_id == branch_id,
                ShiftAssignment.station_id == req.station_id,
                ShiftAssignment.schedule_date == today,
                ShiftAssignment.status == "Published",
            )
            .count()
        )
        total_assigned += min(assigned_today, req.required_count)

    coverage = (
        f"{round((total_assigned / total_required) * 100)}%"
        if total_required
        else "0%"
    )

    conflicts = 0
    assignments_today = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.branch_id == branch_id,
            ShiftAssignment.schedule_date == today,
            ShiftAssignment.status == "Published",
        )
        .all()
    )
    for a in assignments_today:
        if a.start_time is None or a.end_time is None:
            has_any = (
                db.query(Availability)
                .filter(
                    Availability.user_id == a.user_id,
                    Availability.day_of_week == today_name,
                    Availability.valid_from <= today,
                    Availability.valid_to >= today,
                )
                .first()
            )
            if has_any is None:
                conflicts += 1
            continue
        covers_shift = (
            db.query(Availability)
            .filter(
                Availability.user_id == a.user_id,
                Availability.day_of_week == today_name,
                Availability.valid_from <= today,
                Availability.valid_to >= today,
                Availability.start_time <= a.start_time,
                Availability.end_time >= a.end_time,
            )
            .first()
        )
        if covers_shift is None:
            conflicts += 1

    return {
        "team_members": team_members,
        "todays_staff": todays_staff,
        "coverage": coverage,
        "conflicts": conflicts,
    }
