from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.holiday import Holiday
from app.models.user import User
from app.schemas.holiday import (
    HolidayCreate,
    HolidayResponse,
    VALID_HOLIDAY_TYPES,
)

router = APIRouter(prefix="/holidays", tags=["Holidays"])


@router.get("/", response_model=list[HolidayResponse])
def list_holidays(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view holidays.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    holidays = (
        db.query(Holiday)
        .filter(
            (Holiday.branch_id == branch_id) | (Holiday.branch_id.is_(None))
        )
        .order_by(Holiday.holiday_date, Holiday.id)
        .all()
    )
    return holidays


@router.post("/", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
def create_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can create holidays.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    if payload.holiday_type not in VALID_HOLIDAY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid holiday type.",
        )

    existing = (
        db.query(Holiday)
        .filter(
            Holiday.holiday_date == payload.holiday_date,
            (Holiday.branch_id == branch_id) | (Holiday.branch_id.is_(None)),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A holiday already exists for this date.",
        )

    holiday = Holiday(
        holiday_date=payload.holiday_date,
        name=payload.name.strip(),
        holiday_type=payload.holiday_type,
        branch_id=branch_id,
    )
    db.add(holiday)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(holiday)
    return holiday


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can delete holidays.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found.")
    if holiday.branch_id not in (branch_id, None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete holidays for your assigned branch.",
        )
    db.delete(holiday)
    db.commit()
    return None
