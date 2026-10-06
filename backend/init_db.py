from app.database import engine, Base
from app.models.user import User


print("Creating Tables int the database...")

Base.metadata.create_all(bind=engine)

print("Tables created successfully!")