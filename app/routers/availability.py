from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.availability import Availability
from app.models.user import User, UserRole
from app.schemas.availability import AvailabilityCreate, AvailabilityUpdate, AvailabilityResponse
from app.auth.dependencies import get_current_user

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

    # I-update lang kung may ibinigay na bagong value
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