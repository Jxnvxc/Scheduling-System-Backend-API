from sqlalchemy import Column, Date, ForeignKey, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    holiday_date = Column(Date, nullable=False, index=True)
    name = Column(String, nullable=False)
    holiday_type = Column(String, nullable=False)
    branch_id = Column(
        Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    branch = relationship("Branch")
