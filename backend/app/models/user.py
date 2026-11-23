from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Index, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base
from app.models.branch import Branch

class UserRole(str, enum.Enum):
    # Kept to load legacy database rows; startup disables these accounts.
    ADMIN = "admin"
    HEAD = "head"
    MANAGER = "manager"
    EMPLOYEE = "employee"

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_manager_id", "manager_id", unique=True),
        Index("uq_users_employee_number", "employee_number", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    manager_id = Column(String(32), nullable=True)
    employee_number = Column(String(32), nullable=True)
    password_hash = Column(String, nullable=True)  # <-- Ginawang nullable
    full_name = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.EMPLOYEE, nullable=False)
    
    # BAGONG COLUMNS PARA SA CREW
    crew_type = Column(String, nullable=True)          # e.g., "Gel crew, Crew Trainer"
    employment_type = Column(String, nullable=True)    # "Full-time" o "Part-time"
        # BAGONG DAGDAG PARA SA PROFILE
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    branch = relationship("Branch", back_populates="users")
    min_hours = Column(Integer, default=0) # Minimum hours per week
    max_hours = Column(Integer, default=40) # Maximum hours per week
    # Accumulated scheduled hours within the current 15-day pay-period cycle.
    # Recalculated strictly from the active cutoff window; reset only clears
    # this counter and never touches historical schedule records.
    worked_hours = Column(Float, default=0.0)
    # Para sa Skills (Qualified Stations), gagamit tayo ng String na paghihiwalay ng comma (e.g., "1,2,3")
    # Mas simple ito kaysa gumawa ng Many-to-Many table para sa MVP.
    qualified_stations = Column(String, nullable=True) 
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())