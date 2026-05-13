from datetime import datetime, UTC

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.version,
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
