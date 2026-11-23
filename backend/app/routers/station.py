from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.station import Station
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.models.assignment import ShiftAssignment
from app.models.requirement import StaffingRequirement
from app.schemas.station import StationCreate, StationResponse, StationUpdate

router = APIRouter(prefix="/stations", tags=["Stations"])


def _station_response(station: Station, branch_name: str) -> dict:
    return {
        "id": station.id,
        "branch_id": station.branch_id,
        "name": station.name,
        "opening_start_time": station.opening_start_time,
        "opening_end_time": station.opening_end_time,
        "mid_start_time": station.mid_start_time,
        "mid_end_time": station.mid_end_time,
        "closing_start_time": station.closing_start_time,
        "closing_end_time": station.closing_end_time,
        "branch_name": branch_name,
    }


def _remove_station_qualification(qualified_stations: str | None, station_id: int) -> str | None:
    if not qualified_stations:
        return None
    remaining = [
        value.strip()
        for value in qualified_stations.split(",")
        if value.strip() and value.strip() != str(station_id)
    ]
    return ",".join(remaining) or None


@router.post("/", response_model=StationResponse, status_code=status.HTTP_201_CREATED)
def create_station(
    station: StationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(
        current_user,
        unassigned_detail=(
            "Your manager account is not assigned to a branch. "
            "Ask an authorized operator to assign one."
        ),
    )

    # Check kung existing ang branch
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    new_station = Station(
        branch_id=branch_id,
        name=station.name,
        opening_start_time=station.opening_start_time,
        opening_end_time=station.opening_end_time,
        mid_start_time=station.mid_start_time,
        mid_end_time=station.mid_end_time,
        closing_start_time=station.closing_start_time,
        closing_end_time=station.closing_end_time,
    )
    db.add(new_station)
    db.commit()
    db.refresh(new_station)

    return _station_response(new_station, branch.name)

@router.get("/", response_model=List[StationResponse])
def get_all_stations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)

    stations = db.query(Station).filter(Station.branch_id == branch_id).all()

    return [
        _station_response(s, s.branch.name if s.branch else "Unknown")
        for s in stations
    ]


@router.put("/{station_id}", response_model=StationResponse)
def update_station(
    station_id: int,
    station_update: StationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)

    station = db.query(Station).filter(
        Station.id == station_id,
        Station.branch_id == branch_id,
    ).first()
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    for field, value in station_update.model_dump(exclude_unset=True).items():
        setattr(station, field, value)
    db.commit()
    db.refresh(station)
    return _station_response(station, station.branch.name if station.branch else "Unknown")


@router.delete("/{station_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_station(
    station_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(current_user)

    station = db.query(Station).filter(
        Station.id == station_id,
        Station.branch_id == branch_id,
    ).first()
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    has_assignments = db.query(ShiftAssignment.id).filter(
        ShiftAssignment.station_id == station_id,
    ).first()
    if has_assignments:
        raise HTTPException(
            status_code=409,
            detail=(
                "This station is used by published schedules and cannot be removed. "
                "Keep it for schedule history or remove those schedules first."
            ),
        )

    crew_members = db.query(User).filter(
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.qualified_stations.isnot(None),
    ).all()
    for crew_member in crew_members:
        crew_member.qualified_stations = _remove_station_qualification(
            crew_member.qualified_stations,
            station_id,
        )

    db.query(StaffingRequirement).filter(
        StaffingRequirement.station_id == station_id,
    ).delete(synchronize_session=False)
    db.delete(station)
    db.commit()
    return None