from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    audio,
    billing,
    coach,
    dashboard,
    sessions,
    users,
    warmup,
)
from app.core.config import settings
from app.db.base import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="IntonationAI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(coach.router, prefix="/api")
app.include_router(audio.router, prefix="/api")
app.include_router(warmup.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(billing.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
