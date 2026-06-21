"""Тесты Celery-воркера (задача confirm_booking).

Все внешние вызовы мокируются — тесты без Redis/Docker.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.booking import Booking, BookingStatus

# Отдельная in-memory БД для тестов воркера.
SQLITE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    """Создаёт и удаляет таблицы для каждого теста."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    """Возвращает сессию БД для теста."""
    session = SessionLocal()
    yield session
    session.close()


def make_booking(db, status=BookingStatus.PENDING) -> Booking:
    """Создаёт тестовую бронь напрямую в БД."""
    booking = Booking(
        name="Test User",
        booking_datetime=datetime(2025, 12, 1, tzinfo=timezone.utc),
        service_type="consultation",
        status=status,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


class TestConfirmBookingTask:
    """Тесты логики воркера confirm_booking."""

    def _run_task(self, booking_id: str, success: bool, db_session):
        """Запускает логику задачи напрямую (без Celery broker).

        Мокируем: SessionLocal и _simulate_external_service.
        """
        from app import tasks as tasks_module

        # Создаём mock-сессию, которая не закрывается.
        mock_session = MagicMock(wraps=db_session)
        mock_session.close = MagicMock()

        with (
            patch.object(
                tasks_module,
                "SessionLocal",
                return_value=mock_session,
            ),
            patch.object(
                tasks_module,
                "_simulate_external_service",
                return_value=success,
            ),
        ):
            return tasks_module.confirm_booking.run(booking_id)

    def _get_booking(self, db, booking_id):
        """Получает бронь заново из БД."""
        return db.query(Booking).filter(Booking.id == booking_id).first()

    def test_successful_booking_confirmed(self, db):
        """При успехе внешнего сервиса статус меняется на confirmed."""
        booking = make_booking(db)
        booking_id = booking.id

        result = self._run_task(str(booking_id), success=True, db_session=db)

        updated = self._get_booking(db, booking_id)
        assert updated.status == BookingStatus.CONFIRMED
        assert result["status"] == "confirmed"

    def test_failed_booking_status_failed(self, db):
        """При сбое внешнего сервиса статус меняется на failed."""
        booking = make_booking(db)
        booking_id = booking.id

        result = self._run_task(str(booking_id), success=False, db_session=db)

        updated = self._get_booking(db, booking_id)
        assert updated.status == BookingStatus.FAILED
        assert result["status"] == "failed"

    def test_idempotency_confirmed_booking(self, db):
        """Идемпотентность: повторный запуск с confirmed-бронью.

        Не меняет статус и возвращает 'skipped'.
        """
        booking = make_booking(db, status=BookingStatus.CONFIRMED)
        booking_id = booking.id

        result = self._run_task(str(booking_id), success=True, db_session=db)

        updated = self._get_booking(db, booking_id)
        assert updated.status == BookingStatus.CONFIRMED
        assert result["status"] == "skipped"

    def test_idempotency_failed_booking(self, db):
        """Идемпотентность: повторный запуск с failed-бронью.

        Не меняет статус.
        """
        booking = make_booking(db, status=BookingStatus.FAILED)
        booking_id = booking.id

        result = self._run_task(str(booking_id), success=True, db_session=db)

        updated = self._get_booking(db, booking_id)
        assert updated.status == BookingStatus.FAILED
        assert result["status"] == "skipped"

    def test_booking_not_found_returns_error(self, db):
        """Несуществующий booking_id — задача завершается с ошибкой."""
        fake_id = str(uuid.uuid4())

        result = self._run_task(fake_id, success=True, db_session=db)

        assert result["status"] == "error"
        assert result["reason"] == "booking_not_found"

    def test_notification_sent_on_success(self, db):
        """При успехе вызывается mock-уведомление."""
        from app import tasks as tasks_module

        booking = make_booking(db)

        mock_session = MagicMock(wraps=db)
        mock_session.close = MagicMock()

        with (
            patch.object(
                tasks_module,
                "SessionLocal",
                return_value=mock_session,
            ),
            patch.object(
                tasks_module,
                "_simulate_external_service",
                return_value=True,
            ),
            patch.object(
                tasks_module,
                "_send_notification_mock",
            ) as mock_notify,
        ):
            tasks_module.confirm_booking.run(str(booking.id))

        mock_notify.assert_called_once()

    def test_notification_not_sent_on_failure(self, db):
        """При сбое уведомление НЕ отправляется."""
        from app import tasks as tasks_module

        booking = make_booking(db)

        mock_session = MagicMock(wraps=db)
        mock_session.close = MagicMock()

        with (
            patch.object(
                tasks_module,
                "SessionLocal",
                return_value=mock_session,
            ),
            patch.object(
                tasks_module,
                "_simulate_external_service",
                return_value=False,
            ),
            patch.object(
                tasks_module,
                "_send_notification_mock",
            ) as mock_notify,
        ):
            tasks_module.confirm_booking.run(str(booking.id))

        mock_notify.assert_not_called()
