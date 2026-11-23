from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base  # Palitan base sa setup mo (baka app.db o app.config)

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(Integer, ForeignKey("users.id"))
    branch_name = Column(String, index=True)
    status = Column(String, default="Draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship para makuha natin ang pangalan ng manager
    manager = relationship("User")