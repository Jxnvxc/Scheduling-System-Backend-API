from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.station import Station
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.schemas.station import StationCreate, StationResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/stations", tags=["Stations"])

@router.post("/", response_model=StationResponse, status_code=status.HTTP_201_CREATED)
def create_station(
    station: StationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # I-SECURITY CHECK: Kung Manager, pwede lang siya gumawa ng station sa branch niya.
    if current_user.role == UserRole.MANAGER and station.branch_id != current_user.branch_id:
        raise HTTPException(status_code=403, detail="You can only add stations to your assigned branch")

    # Check kung existing ang branch
    branch = db.query(Branch).filter(Branch.id == station.branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    new_station = Station(branch_id=station.branch_id, name=station.name)
    db.add(new_station)
    db.commit()
    db.refresh(new_station)

    return {
        "id": new_station.id,
        "branch_id": new_station.branch_id,
        "name": new_station.name,
        "branch_name": branch.name
    }

@router.get("/", response_model=List[StationResponse])
def get_all_stations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # I-SECURITY CHECK: Filter ang makikita base sa role
    if current_user.role == UserRole.ADMIN:
        # Admin kita lahat
        stations = db.query(Station).all()
    else:
        # Manager, kita lang yung stations sa branch niya
        stations = db.query(Station).filter(Station.branch_id == current_user.branch_id).all()

    return [
        {
            "id": s.id,
            "branch_id": s.branch_id,
            "name": s.name,
            "branch_name": s.branch.name if s.branch else "Unknown"
        }
        for s in stations
    ]