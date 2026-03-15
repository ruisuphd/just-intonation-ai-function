import os

from fastapi import APIRouter

router = APIRouter(tags=["health"])

VERSION = os.getenv("APP_VERSION", "1.0.0")


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": VERSION,
        "service": "automark-api",
    }
