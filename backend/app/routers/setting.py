from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.setting import SystemSetting
from app.models.user import User
from app.schemas.setting import (
    PRE_HOLIDAY_MIRROR_KEY,
    PRE_HOLIDAY_MIRROR_OFF,
    PRE_HOLIDAY_MIRROR_ON,
    SystemSettingResponse,
    SystemSettingUpdate,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


def _get_setting(
    db: Session, branch_id: int, key: str
) -> SystemSetting | None:
    return (
        db.query(SystemSetting)
        .filter(
            SystemSetting.key == key,
            (SystemSetting.branch_id == branch_id) | (SystemSetting.branch_id.is_(None)),
        )
        .first()
    )


@router.get("/pre-holiday-mirror", response_model=SystemSettingResponse)
def get_pre_holiday_mirror(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view settings.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    setting = _get_setting(db, branch_id, PRE_HOLIDAY_MIRROR_KEY)
    if setting is None:
        setting = SystemSetting(
            branch_id=branch_id,
            key=PRE_HOLIDAY_MIRROR_KEY,
            value=PRE_HOLIDAY_MIRROR_OFF,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.put("/pre-holiday-mirror", response_model=SystemSettingResponse)
def put_pre_holiday_mirror(
    payload: SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can update settings.",
        unassigned_detail="Your manager account is not assigned to a branch.",
    )
    value = payload.value.strip().upper()
    if value not in (PRE_HOLIDAY_MIRROR_ON, PRE_HOLIDAY_MIRROR_OFF):
        raise HTTPException(
            status_code=422,
            detail="Value must be ON or OFF.",
        )

    setting = _get_setting(db, branch_id, PRE_HOLIDAY_MIRROR_KEY)
    if setting is None:
        setting = SystemSetting(
            branch_id=branch_id,
            key=PRE_HOLIDAY_MIRROR_KEY,
            value=value,
        )
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    db.refresh(setting)
    return setting
