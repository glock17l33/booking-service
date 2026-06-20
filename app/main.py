from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.logging_config import configure_logging
from app.middleware import RateLimitMiddleware
from app.routers.bookings import router as bookings_router

# Настраиваем structured JSON logging до создания приложения
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Создаёт таблицы при старте (если не существуют).
    В production лучше использовать Alembic-миграции.
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Booking Service API",
    description="REST API для записи на встречи с асинхронной обработкой через Celery.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (для dev-окружения)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# Роутеры
app.include_router(bookings_router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "env": settings.app_env}
