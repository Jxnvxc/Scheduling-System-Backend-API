from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False) # e.g., Cashier, Kitchen, Grill

    # Relationship para makuha natin yung branch details kung kailangan
    branch = relationship("Branch")