from datetime import time

from sqlalchemy import Column, ForeignKey, Integer, String, Time, text
from sqlalchemy.orm import relationship
from app.database import Base


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False) # e.g., Cashier, Kitchen, Grill
    opening_start_time = Column(
        Time,
        nullable=False,
        default=time(8, 0),
        server_default=text("'08:00:00'"),
    )
    opening_end_time = Column(
        Time,
        nullable=False,
        default=time(16, 0),
        server_default=text("'16:00:00'"),
    )
    mid_start_time = Column(
        Time,
        nullable=False,
        default=time(12, 0),
        server_default=text("'12:00:00'"),
    )
    mid_end_time = Column(
        Time,
        nullable=False,
        default=time(20, 0),
        server_default=text("'20:00:00'"),
    )
    closing_start_time = Column(
        Time,
        nullable=False,
        default=time(14, 0),
        server_default=text("'14:00:00'"),
    )
    closing_end_time = Column(
        Time,
        nullable=False,
        default=time(22, 0),
        server_default=text("'22:00:00'"),
    )

    # Relationship para makuha natin yung branch details kung kailangan
    branch = relationship("Branch")

    priority = Column(Integer, nullable=False, default=2)