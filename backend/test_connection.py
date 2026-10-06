import os 
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

print(f"Testing connection to: {DATABASE_URL.split('@')[1]}")

try:
    engine = create_engine(DATABASE_URL)
    print("Connection successful!")
    with engine.connect() as connection:
        print(f"SUCCESS: connected to PostgreSQL DATABASE!")
except Exception as e:
    print(f"FAILED!")
    print(f"Error connecting to database: {e}")