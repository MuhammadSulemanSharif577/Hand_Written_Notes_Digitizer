from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, engine, ensure_history_summary_column
from .routers import history, upload, users
from .services.ocr_runtime import start_ocr_model_warmup

# Create database tables if they do not exist
Base.metadata.create_all(bind=engine)
ensure_history_summary_column()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_ocr_model_warmup()
    yield


app = FastAPI(title="Handwritten Digitizer API", lifespan=lifespan)

# Enable CORS for Flutter frontend clients (Android emulator, Web, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API module routers
app.include_router(users.router)
app.include_router(upload.router)
app.include_router(history.router)

@app.get("/")
def home():
    return {"message": "Backend is working!"}
