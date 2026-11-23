from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import os
import base64
from datetime import datetime

from app.database import get_db
from app.models.absence import Absence, AbsenceStatus
from app.models.user import User, UserRole
from app.models.branch import Branch
from app.schemas.absence import (
    AbsenceCreate,
    AbsenceUpdate,
    AbsenceApprove,
    AbsenceReject,
    AbsenceResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.branch_access import require_manager_branch_id

router = APIRouter(prefix="/absences", tags=["Absences"])

UPLOAD_DIR = "uploads/absences"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _save_proof_image(base64_data: str, absence_id: int) -> str:
    """Save base64 image to disk and return file path."""
    if not base64_data:
        return None
    try:
        header, encoded = base64_data.split(",", 1)
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "gif" in header:
            ext = "gif"
        filename = f"absence_{absence_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(encoded))
        return filepath
    except Exception:
        return None


def _to_response(absence: Absence, db: Session) -> AbsenceResponse:
    employee = db.query(User).filter(User.id == absence.employee_id).first()
    approver = db.query(User).filter(User.id == absence.approved_by).first() if absence.approved_by else None
    return AbsenceResponse(
        id=absence.id,
        employee_id=absence.employee_id,
        branch_id=absence.branch_id,
        absence_date=absence.absence_date,
        reason=absence.reason,
        proof_image=absence.proof_image,
        status=absence.status.value if isinstance(absence.status, AbsenceStatus) else absence.status,
        approved_by=absence.approved_by,
        approved_at=absence.approved_at.isoformat() if absence.approved_at else None,
        created_at=absence.created_at.isoformat() if absence.created_at else None,
        updated_at=absence.updated_at.isoformat() if absence.updated_at else None,
        employee_name=employee.full_name if employee else None,
        approver_name=approver.full_name if approver else None,
    )


# 1. CREW MAG-REQUEST NG ABSENCE
@router.post("/", response_model=AbsenceResponse, status_code=status.HTTP_201_CREATED)
def request_absence(
    req: AbsenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.EMPLOYEE:
        raise HTTPException(status_code=403, detail="Only crew can request absence")

    if current_user.branch_id is None:
        raise HTTPException(status_code=400, detail="Employee not assigned to a branch")

    absence = Absence(
        employee_id=current_user.id,
        branch_id=current_user.branch_id,
        absence_date=req.absence_date,
        reason=req.reason,
        status=AbsenceStatus.PENDING,
    )

    db.add(absence)
    db.commit()
    db.refresh(absence)

    # Save proof image if provided
    if req.proof_image:
        filepath = _save_proof_image(req.proof_image, absence.id)
        absence.proof_image = filepath
        db.commit()

    return _to_response(absence, db)


# 2. CREW MAKITA ANG SARILING ABSENCES
@router.get("/my", response_model=List[AbsenceResponse])
def get_my_absences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    absences = db.query(Absence).filter(
        Absence.employee_id == current_user.id
    ).order_by(Absence.absence_date.desc()).all()
    return [_to_response(a, db) for a in absences]


# 3. MANAGER MAKITA ANG LAHAT NG ABSENGE SA BRANCH
@router.get("/branch", response_model=List[AbsenceResponse])
def get_branch_absences(
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)

    query = db.query(Absence).filter(Absence.branch_id == branch_id)
    if status:
        query = query.filter(Absence.status == AbsenceStatus(status))
    absences = query.order_by(Absence.absence_date.desc()).all()
    return [_to_response(a, db) for a in absences]


# 4. MANAGER APPROVE
@router.put("/{absence_id}/approve", response_model=AbsenceResponse)
def approve_absence(
    absence_id: int,
    req: AbsenceApprove = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)

    absence = db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.branch_id == branch_id
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")

    absence.status = AbsenceStatus.APPROVED
    absence.approved_by = current_user.id
    absence.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(absence)
    return _to_response(absence, db)


# 5. MANAGER REJECT
@router.put("/{absence_id}/reject", response_model=AbsenceResponse)
def reject_absence(
    absence_id: int,
    req: AbsenceReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    branch_id = require_manager_branch_id(current_user)

    absence = db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.branch_id == branch_id
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")

    absence.status = AbsenceStatus.REJECTED
    absence.approved_by = current_user.id
    absence.approved_at = datetime.utcnow()
    absence.reason = (absence.reason or "") + f" [Rejected: {req.reason}]"
    db.commit()
    db.refresh(absence)
    return _to_response(absence, db)


# 6. CANCEL REQUEST (CREW)
@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_absence(
    absence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    absence = db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.employee_id == current_user.id
    ).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")
    if absence.status != AbsenceStatus.PENDING:
        raise HTTPException(status_code=400, detail="Cannot cancel approved/rejected absence")

    db.delete(absence)
    db.commit()
    return None