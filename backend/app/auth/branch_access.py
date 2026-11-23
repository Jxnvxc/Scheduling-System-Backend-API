from fastapi import HTTPException

from app.models.user import User, UserRole


def require_manager_branch_id(
    current_user: User,
    *,
    manager_detail: str = "Not authorized",
    unassigned_detail: str = "Manager account is not assigned to a branch.",
) -> int:
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=403, detail=manager_detail)
    if current_user.branch_id is None:
        raise HTTPException(status_code=409, detail=unassigned_detail)
    return current_user.branch_id
