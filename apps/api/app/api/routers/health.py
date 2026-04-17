from datetime import datetime, UTC

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "v1",
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
