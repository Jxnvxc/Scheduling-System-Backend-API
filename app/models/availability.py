from sqlalchemy import Column, Integer, String, Time, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Availability(Base):
    __tablename__ = "availabilities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # BAGONG FIELDS
    day_of_week = Column(String, nullable=False)   # e.g., "Monday", "Tuesday"
    start_time = Column(Time, nullable=False)      # e.g., "08:00:00"
    end_time = Column(Time, nullable=False)        # e.g., "16:00:00"
    valid_from = Column(Date, nullable=False)      # e.g., "2026-10-18"
    valid_to = Column(Date, nullable=False)        # e.g., "2027-04-18" (6 months later)

    user = relationship("User")