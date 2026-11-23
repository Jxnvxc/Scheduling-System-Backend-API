from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from app.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(
        Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
    key = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    branch = relationship("Branch")
