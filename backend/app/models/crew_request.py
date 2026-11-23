from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class CrewRequest(Base):
    __tablename__ = "crew_requests"
    __table_args__ = (
        Index("ix_crew_requests_status_type", "status", "request_type"),
        Index("ix_crew_requests_branch_status", "branch_id", "status"),
        Index("ix_crew_requests_requester", "requester_id"),
        Index("ix_crew_requests_target", "target_user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    request_type = Column(String(20), nullable=False)
    status = Column(String(24), nullable=False, default="pending_manager")
    requester_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    requester_assignment_id = Column(
        Integer, ForeignKey("shift_assignments.id", ondelete="SET NULL"), nullable=True
    )
    target_assignment_id = Column(
        Integer, ForeignKey("shift_assignments.id", ondelete="SET NULL"), nullable=True
    )
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    reason = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
