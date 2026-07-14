from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from database import engine, Base, ensure_history_summary_column
import routers.users
import routers.upload
import routers.history

# Create database tables if they do not exist
Base.metadata.create_all(bind=engine)
ensure_history_summary_column()

app = FastAPI(title="Handwritten Digitizer API")

# Enable CORS for Flutter frontend clients (Android emulator, Web, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API module routers
app.include_router(routers.users.router)
app.include_router(routers.upload.router)
app.include_router(routers.history.router)

@app.get("/")
def home():
    return {"message": "Backend is working!"}
