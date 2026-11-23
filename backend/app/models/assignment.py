from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.orm import relationship
from app.database import Base

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    
    schedule_date = Column(Date, nullable=False)
    shift_name = Column(String, nullable=False) # Opening, Mid, Closing
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    status = Column(String, default="Published") # Draft or Published
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User")
    branch = relationship("Branch")
    station = relationship("Station")