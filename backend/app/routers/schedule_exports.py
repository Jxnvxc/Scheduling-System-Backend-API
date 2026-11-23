import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.branch_access import require_manager_branch_id
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.schemas.schedule_export import ScheduleExportRequest
from app.services.roster_export import (
    ScheduleRosterRow,
    build_schedule_docx,
    build_schedule_pdf,
    roster_rows,
)
from app.services.schedule_export import build_schedule_workbook
from app.services.scheduling import employee_is_qualified
from app.services.station_shifts import effective_station_shifts

router = APIRouter(prefix="/schedules", tags=["Schedules"])
EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
PDF_CONTENT_TYPE = "application/pdf"


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return normalized or "branch"


def _resolve_schedule_export(
    payload: ScheduleExportRequest,
    db: Session,
    current_user: User,
) -> tuple[str, list[ScheduleRosterRow]]:
    branch_id = require_manager_branch_id(current_user)
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assigned branch no longer exists.",
        )

    station_ids = {row.station_id for row in payload.rows}
    stations = db.query(Station).filter(
        Station.branch_id == branch_id,
        Station.id.in_(station_ids),
    ).all()
    station_by_id = {station.id: station for station in stations}
    if station_ids != set(station_by_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="All stations must belong to your assigned branch.",
        )

    user_ids = {
        user_id
        for row in payload.rows
        for user_id in row.assigned_user_ids
    }
    employees = db.query(User).filter(
        User.id.in_(user_ids),
        User.branch_id == branch_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
    ).all() if user_ids else []
    employee_by_id = {employee.id: employee for employee in employees}
    if user_ids != set(employee_by_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="All assigned crew must be active employees in your branch.",
        )

    requirement_rows = db.query(StaffingRequirement).filter(
        StaffingRequirement.branch_id == branch_id,
        StaffingRequirement.station_id.in_(station_ids),
    ).all()
    station_shifts = effective_station_shifts(stations, requirement_rows)
    shifts_by_key = {
        (shift.station_id, shift.name): shift
        for shift in station_shifts
    }

    export_rows: list[ScheduleRosterRow] = []
    for row in payload.rows:
        station = station_by_id[row.station_id]
        shift = shifts_by_key.get((station.id, row.shift_name))
        if shift is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="All exported shifts must be configured for their station.",
            )
        start_time, end_time = shift.start_time, shift.end_time
        assigned_names = tuple(
            _crew_display_name(employee_by_id[user_id])
            for user_id in row.assigned_user_ids
        )
        if any(
            not employee_is_qualified(employee_by_id[user_id], station.id)
            for user_id in row.assigned_user_ids
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assigned crew must be qualified for the selected station.",
            )
        required = shift.required_count
        assigned = len(assigned_names)
        export_rows.append(
            ScheduleRosterRow(
                station=station.name,
                shift=row.shift_name,
                start_time=start_time,
                end_time=end_time,
                crew_names=assigned_names,
                coverage=f"{assigned} / {required}",
                status="Complete" if assigned == required else "Shortage",
            )
        )

    return branch.name, export_rows


def _crew_display_name(employee: User) -> str:
    crew_type = employee.crew_type.strip() if employee.crew_type else ""
    if crew_type:
        return f"{employee.full_name} ({crew_type})"
    return employee.full_name


def _workbook_rows(rows: list[ScheduleRosterRow]) -> list[dict[str, str]]:
    return [
        {
            "station": station,
            "crew": crew,
            "schedule": schedule,
        }
        for station, crew, schedule, _ in roster_rows(rows)
    ]


def _file_response(
    file_bytes: bytes,
    media_type: str,
    filename: str,
) -> Response:
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export.xlsx")
def export_schedule(
    payload: ScheduleExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_name, rows = _resolve_schedule_export(payload, db, current_user)
    file_bytes = build_schedule_workbook(
        branch_name=branch_name,
        schedule_date=payload.schedule_date.isoformat(),
        rows=_workbook_rows(rows),
    )
    filename = (
        f"smartshift-schedule-{_safe_filename(branch_name)}-"
        f"{payload.schedule_date.isoformat()}.xlsx"
    )
    return _file_response(file_bytes, EXCEL_CONTENT_TYPE, filename)


@router.post("/export.docx")
def export_schedule_docx(
    payload: ScheduleExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_name, rows = _resolve_schedule_export(payload, db, current_user)
    file_bytes = build_schedule_docx(
        branch_name,
        payload.schedule_date,
        rows,
    )
    filename = (
        f"smartshift-schedule-{_safe_filename(branch_name)}-"
        f"{payload.schedule_date.isoformat()}.docx"
    )
    return _file_response(file_bytes, DOCX_CONTENT_TYPE, filename)


@router.post("/export.pdf")
def export_schedule_pdf(
    payload: ScheduleExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_name, rows = _resolve_schedule_export(payload, db, current_user)
    file_bytes = build_schedule_pdf(
        branch_name,
        payload.schedule_date,
        rows,
    )
    filename = (
        f"smartshift-schedule-{_safe_filename(branch_name)}-"
        f"{payload.schedule_date.isoformat()}.pdf"
    )
    return _file_response(file_bytes, PDF_CONTENT_TYPE, filename)
