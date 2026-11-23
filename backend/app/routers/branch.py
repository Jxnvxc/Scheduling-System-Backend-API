from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User
from app.schemas.branch import BranchResponse

router = APIRouter(prefix="/branches", tags=["Branches"])


@router.get("/", response_model=list[BranchResponse])
def get_my_branch(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_manager_branch_id(
        current_user,
        manager_detail="Only managers can view branch details",
        unassigned_detail=(
            "Your manager account is not assigned to a branch. "
            "Ask an authorized operator to assign one."
        ),
    )

    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if branch is None:
        raise HTTPException(status_code=409, detail="Your assigned branch no longer exists.")
    return [branch]
