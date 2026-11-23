from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.database import (
    engine,
    Base,
    SessionLocal,
    migrate_head_user_role,
    migrate_manager_id,
    migrate_employee_number,
    migrate_branch_name_ci_unique,
    migrate_station_operating_hours,
    migrate_shift_assignment_acknowledgment,
    migrate_staffing_requirement_unique,
    migrate_station_shift_templates,
    migrate_standard_station_shift_names,
    migrate_crew_request_branch,
    migrate_staffing_requirement_enabled,
    migrate_crew_worked_hours,
    migrate_holidays_table,
    migrate_system_settings_table,
    migrate_station_priority,
    migrate_shift_minimum_crew,
)
from app.config import settings
from app.models.user import User, UserRole
from app.routers import (
    absence,
    availability,
    branch,
    crew,
    crew_requests,
    head,
    holiday,
    schedule,
    schedule_exports,
    setting,
    staffing_requirement,
    stats,
    station,
    user,
)
import app.models.assignment
import app.models.absence
import app.models.crew_request
import app.models.holiday
import app.models.setting
app = FastAPI(
    title="Scheduling API",
    description="Backend para sa SmartShift Scheduling System",
    version="1.0.0"
)

# I-configure ang CORS para payagan ang frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Isaksak ang routers
app.include_router(user.router)
app.include_router(absence.router)
app.include_router(schedule.router)  # ← ITO ANG KULANG!
app.include_router(schedule_exports.router)  # ← ITO ANG KULANG!
app.include_router(holiday.router)
app.include_router(setting.router)
app.include_router(stats.router)
app.include_router(crew.router)
app.include_router(crew_requests.router)
app.include_router(availability.router)
app.include_router(branch.router)
app.include_router(station.router)
app.include_router(head.router)
app.include_router(staffing_requirement.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIR / "assets"),
    name="frontend-assets",
)
app.mount(
    "/pages",
    StaticFiles(directory=FRONTEND_DIR / "pages"),
    name="frontend-pages",
)

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
app.mount(
    "/uploads",
    StaticFiles(directory=UPLOADS_DIR),
    name="uploads",
)

# Siguraduhing naka-create ang lahat ng tables sa database
Base.metadata.create_all(bind=engine)
migrate_head_user_role()
migrate_manager_id()
migrate_employee_number()
migrate_branch_name_ci_unique()
migrate_station_operating_hours()
migrate_shift_assignment_acknowledgment()
migrate_staffing_requirement_unique()
migrate_station_shift_templates()
migrate_standard_station_shift_names()
migrate_crew_request_branch()
migrate_staffing_requirement_enabled()
migrate_crew_worked_hours()
migrate_holidays_table()
migrate_system_settings_table()
migrate_station_priority()
migrate_shift_minimum_crew()

@app.on_event("startup")
def disable_legacy_admin_accounts():
    db = SessionLocal()
    try:
        db.query(User).filter(
            User.role == UserRole.ADMIN
        ).update({User.is_active: False}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.get("/")
def read_root():
    return RedirectResponse(url="/pages/index.html")

@app.get("/health")
def health_check():
    return {"status": "ok", "database": "connected"}