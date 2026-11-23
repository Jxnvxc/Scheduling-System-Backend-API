from datetime import time

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Time, text
from sqlalchemy.orm import relationship
from app.database import Base


class StaffingRequirement(Base):
    __tablename__ = "staffing_requirements"
    __table_args__ = (
        Index(
            "uq_staffing_requirement_shift",
            "branch_id",
            "station_id",
            "shift_type",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)

    shift_type = Column(String(100), nullable=False)
    start_time = Column(
        Time,
        nullable=False,
        default=time(8, 0),
        server_default=text("'08:00:00'"),
    )
    end_time = Column(
        Time,
        nullable=False,
        default=time(16, 0),
        server_default=text("'16:00:00'"),
    )
    required_count = Column(Integer, nullable=False, default=1, server_default=text("1"))
    minimum_crew = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    branch = relationship("Branch")
    station = relationship("Station")