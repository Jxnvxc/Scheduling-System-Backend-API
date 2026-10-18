from app.database import engine, Base
# I-import lahat ng models para makilala sila ni Base
from app.models.user import User
from app.models.availability import Availability
from app.models.branch import Branch
from app.models.schedule import Schedule
from app.models.station import Station

print("Creating new tables (kung wala pa)...")
Base.metadata.create_all(bind=engine)
print("Done! ✅")