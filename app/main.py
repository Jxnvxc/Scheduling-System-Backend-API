from fastapi import FastAPI
from app.database import engine, Base
from app.routers import user

app = FastAPI(
  title = "Automated Scheduling API",
  description = "Backen para sa Scheduling System",
  version = " 1.0.0"
)
app.include_router(user.router)


@app.get("/")
def read_root():
  return {"message": "Welcome to Scheduling API"}

@app.get("/health")
def health_check():
  return {"Status": "Okay", "database": "connected"}

