from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import user, schedule  # Import both
from app.routers import user, schedule, stats
from app.routers import user, schedule, stats, crew 

app = FastAPI(
    title="Scheduling API",
    description="Backend para sa SmartShift Scheduling System",
    version="1.0.0"
)

# I-configure ang CORS para payagan ang frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Sa production, palitan ito ng specific URL ng frontend mo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Isaksak ang routers
app.include_router(user.router)
app.include_router(schedule.router)  # ← ITO ANG KULANG!
app.include_router(stats.router)
app.include_router(crew.router)
# Siguraduhing naka-create ang lahat ng tables sa database
Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"message": "Welcome to SmartShift API! 🚀"}

@app.get("/health")
def health_check():
    return {"status": "ok", "database": "connected"}