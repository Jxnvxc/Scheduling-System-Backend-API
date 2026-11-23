from sqlalchemy import Column, Index, Integer, String, Time, column, func
from sqlalchemy.orm import relationship
from app.database import Base

class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        Index(
            "uq_branches_name_ci",
            func.lower(func.trim(column("name"))),
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    
    # Operating Hours
    opening_time = Column(Time, nullable=False)  # Halimbawa: 08:00:00
    closing_time = Column(Time, nullable=False)  # Halimbawa: 22:00:00
    
    # Prep and Closing (in minutes)
    prep_time_minutes = Column(Integer, default=30)     # Halimbawa: 30 mins bago mag-open
    closing_time_minutes = Column(Integer, default=30)  # Halimbawa: 30 mins para maglinis

    # Relationship sa mga employees
    users = relationship("User", back_populates="branch")
    