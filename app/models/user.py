from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
import enum
from app.database import Base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)  # <-- Ginawang nullable
    full_name = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.EMPLOYEE, nullable=False)
    
    # BAGONG COLUMNS PARA SA CREW
    crew_type = Column(String, nullable=True)          # e.g., "Gel crew, Crew Trainer"
    employment_type = Column(String, nullable=True)    # "Full-time" o "Part-time"
        # BAGONG DAGDAG PARA SA PROFILE
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    min_hours = Column(Integer, default=0) # Minimum hours per week
    max_hours = Column(Integer, default=40) # Maximum hours per week
    # Para sa Skills (Qualified Stations), gagamit tayo ng String na paghihiwalay ng comma (e.g., "1,2,3")
    # Mas simple ito kaysa gumawa ng Many-to-Many table para sa MVP.
    qualified_stations = Column(String, nullable=True) 
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())