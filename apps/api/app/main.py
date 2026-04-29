from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.annotations import router as annotations_router
from app.api.routers.auth import router as auth_router
from app.api.routers.feeds import router as feeds_router
from app.api.routers.health import router as health_router
from app.api.routers.items import router as items_router
from app.api.routers.organization import router as organization_router
from app.api.routers.podcasts import router as podcasts_router
from app.api.routers.providers import router as providers_router
from app.api.routers.settings import router as settings_router
from app.api.routers.tasks import router as tasks_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(feeds_router, prefix=settings.api_prefix)
app.include_router(annotations_router, prefix=settings.api_prefix)
app.include_router(items_router, prefix=settings.api_prefix)
app.include_router(organization_router, prefix=settings.api_prefix)
app.include_router(podcasts_router, prefix=settings.api_prefix)
app.include_router(providers_router, prefix=settings.api_prefix)
app.include_router(settings_router, prefix=settings.api_prefix)
app.include_router(tasks_router, prefix=settings.api_prefix)
