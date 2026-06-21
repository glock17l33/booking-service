"""
Конфигурация pytest.

Используем SQLite in-memory вместо PostgreSQL — тесты работают
без Docker и без поднятого стека.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Создаём таблицы перед каждым тестом и удаляем после."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Сессия БД для прямой работы в тестах."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient с подменённой БД и отключённым lifespan.
    """
    # Подменяем engine в модуле database ДО импорта app
    import app.database as database_module
    database_module.engine = engine

    # Теперь импортируем app
    from app.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
