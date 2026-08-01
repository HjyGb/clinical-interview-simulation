"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, assessments, cases, sessions
from app.config import settings
from app.database import Base, engine

app = FastAPI(title=settings.app_name, debug=settings.debug)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(sessions.router)
app.include_router(assessments.router)


@app.on_event("startup")
def on_startup():
    """Create tables on startup (dev convenience; use Alembic in production)."""
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.app_name}
