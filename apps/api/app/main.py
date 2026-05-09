import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.annotations import router as annotations_router
from app.api.routers.auth import router as auth_router
from app.api.routers.daily_news import router as daily_news_router
from app.api.routers.feeds import router as feeds_router
from app.api.routers.health import router as health_router
from app.api.routers.items import router as items_router
from app.api.routers.mcp import router as mcp_router
from app.api.routers.organization import router as organization_router
from app.api.routers.podcasts import router as podcasts_router
from app.api.routers.providers import router as providers_router
from app.api.routers.settings import router as settings_router
from app.api.routers.tasks import router as tasks_router
from app.core.config import get_settings
from app.services.daily_news_scheduler_service import run_daily_news_generation_loop
from app.services.feed_refresh_service import run_feed_refresh_loop

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = app
    refresh_task: asyncio.Task[None] | None = None
    daily_news_task: asyncio.Task[None] | None = None
    if settings.feed_refresh_enabled:
        refresh_task = asyncio.create_task(
            run_feed_refresh_loop(
                settings.feed_refresh_interval_seconds,
                settings.feed_refresh_startup_delay_seconds,
            )
        )
    if settings.daily_news_generation_enabled:
        daily_news_task = asyncio.create_task(
            run_daily_news_generation_loop(
                settings.daily_news_generation_hour,
                settings.daily_news_generation_timezone,
            )
        )
    try:
        yield
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await refresh_task
        if daily_news_task is not None:
            daily_news_task.cancel()
            with suppress(asyncio.CancelledError):
                await daily_news_task


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(daily_news_router, prefix=settings.api_prefix)
app.include_router(feeds_router, prefix=settings.api_prefix)
app.include_router(annotations_router, prefix=settings.api_prefix)
app.include_router(items_router, prefix=settings.api_prefix)
app.include_router(mcp_router, prefix=settings.api_prefix)
app.include_router(organization_router, prefix=settings.api_prefix)
app.include_router(podcasts_router, prefix=settings.api_prefix)
app.include_router(providers_router, prefix=settings.api_prefix)
app.include_router(settings_router, prefix=settings.api_prefix)
app.include_router(tasks_router, prefix=settings.api_prefix)
