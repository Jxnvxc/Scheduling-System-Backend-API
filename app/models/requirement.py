from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class StaffingRequirement(Base):
    __tablename__ = "staffing_requirements"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    
    shift_type = Column(String, nullable=False) # "Opening", "Mid", "Closing"
    required_count = Column(Integer, default=1) # Ilan ang kailangan?

    branch = relationship("Branch")
    station = relationship("Station")