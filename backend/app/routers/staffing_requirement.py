from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User
from app.schemas.staffing_requirement import (
    StaffingRequirementBulkUpdate,
    StaffingRequirementResponse,
    STANDARD_SHIFT_NAMES,
)
from app.services.station_shifts import effective_station_shifts

router = APIRouter(prefix="/staffing-requirements", tags=["Staffing Requirements"])


def _branch_requirements(
    db: Session,
    branch_id: int,
) -> list[StaffingRequirementResponse]:
    stations = (
        db.query(Station)
        .filter(Station.branch_id == branch_id)
        .order_by(Station.name, Station.id)
        .all()
    )
    saved_requirements = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).all()
    return [
        StaffingRequirementResponse(
            station_id=shift.station_id,
            station_name=shift.station_name,
            shift_type=shift.name,
            start_time=shift.start_time,
            end_time=shift.end_time,
            required_count=shift.required_count,
            enabled=shift.enabled,
        )
        for shift in effective_station_shifts(
            stations,
            saved_requirements,
            include_disabled=True,
        )
    ]


@router.get("/", response_model=list[StaffingRequirementResponse])
def get_staffing_requirements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    return _branch_requirements(db, branch_id)


@router.put("/", response_model=list[StaffingRequirementResponse])
def update_staffing_requirements(
    payload: StaffingRequirementBulkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)
    station_ids = {item.station_id for item in payload.requirements}
    stations = db.query(Station).filter(Station.branch_id == branch_id).all()
    valid_station_ids = {station.id for station in stations}
    if station_ids != valid_station_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Configure at least one shift for every station in your "
                "assigned branch."
            ),
        )
    shifts_by_station: dict[int, set[str]] = {}
    for item in payload.requirements:
        shifts_by_station.setdefault(item.station_id, set()).add(item.shift_type)
    if any(
        shifts_by_station.get(station_id, set()) != set(STANDARD_SHIFT_NAMES)
        for station_id in valid_station_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Configure at least one shift for every station in your "
                "assigned branch."
            ),
        )

    enabled_by_station: dict[int, list[str]] = {}
    for item in payload.requirements:
        if item.enabled:
            enabled_by_station.setdefault(item.station_id, []).append(item.shift_type)
    for station_id in valid_station_ids:
        if not enabled_by_station.get(station_id):
            station = next(
                s for s in stations if s.id == station_id
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Station '{station.name}' must have at least one enabled shift. "
                    "Piliin o kusa ang bago i-save."
                ),
            )

    db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
    ).delete(synchronize_session=False)
    db.add_all(
        [
            StaffingRequirement(
                branch_id=branch_id,
                station_id=item.station_id,
                shift_type=item.shift_type,
                start_time=item.start_time,
                end_time=item.end_time,
                required_count=item.required_count,
                enabled=item.enabled,
            )
            for item in payload.requirements
        ]
    )

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Staffing requirements changed concurrently. Reload and try again.",
        ) from error

    return _branch_requirements(db, branch_id)
