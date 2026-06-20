"""
Тесты Celery-воркера (задача confirm_booking).
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

# Отдельная in-memory БД для тестов воркера
SQLITE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def make_booking(db, status=BookingStatus.pending) -> Booking:
    """Создаёт тестовую бронь напрямую в БД."""
    booking = Booking(
        name="Test User",
        datetime=datetime(2025, 12, 1, tzinfo=timezone.utc),
        service_type="consultation",
        status=status,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────────────────────────────────────────
# Тесты логики воркера
# ──────────────────────────────────────────────────────────────────────────────

class TestConfirmBookingTask:
    def _run_task(self, booking_id: str, success: bool, db_session):
        """
        Запускает логику задачи напрямую (без Celery broker).
        Мокируем: SessionLocal и _simulate_external_service.
        """
        from app import tasks as tasks_module

        with patch.object(tasks_module, "SessionLocal", return_value=db_session), \
             patch.object(tasks_module, "_simulate_external_service", return_value=success):
            # Вызываем функцию напрямую, минуя Celery
            return tasks_module.confirm_booking.run(booking_id)

    def test_successful_booking_confirmed(self, db):
        """При успехе внешнего сервиса статус меняется на confirmed."""
        booking = make_booking(db)
        result = self._run_task(str(booking.id), success=True, db_session=db)

        db.refresh(booking)
        assert booking.status == BookingStatus.confirmed
        assert result["status"] == "confirmed"

    def test_failed_booking_status_failed(self, db):
        """При сбое внешнего сервиса статус меняется на failed."""
        booking = make_booking(db)
        result = self._run_task(str(booking.id), success=False, db_session=db)

        db.refresh(booking)
        assert booking.status == BookingStatus.failed
        assert result["status"] == "failed"

    def test_idempotency_confirmed_booking(self, db):
        """
        Идемпотентность: повторный запуск с confirmed-бронью
        не меняет статус и возвращает 'skipped'.
        """
        booking = make_booking(db, status=BookingStatus.confirmed)
        result = self._run_task(str(booking.id), success=True, db_session=db)

        db.refresh(booking)
        assert booking.status == BookingStatus.confirmed  # не изменился
        assert result["status"] == "skipped"

    def test_idempotency_failed_booking(self, db):
        """
        Идемпотентность: повторный запуск с failed-бронью
        не меняет статус.
        """
        booking = make_booking(db, status=BookingStatus.failed)
        result = self._run_task(str(booking.id), success=True, db_session=db)

        db.refresh(booking)
        assert booking.status == BookingStatus.failed  # не изменился
        assert result["status"] == "skipped"

    def test_booking_not_found_returns_error(self, db):
        """Несуществующий booking_id — задача завершается с ошибкой, не падает."""
        fake_id = str(uuid.uuid4())
        result = self._run_task(fake_id, success=True, db_session=db)
        assert result["status"] == "error"
        assert result["reason"] == "booking_not_found"

    def test_notification_sent_on_success(self, db):
        """При успехе вызывается mock-уведомление."""
        from app import tasks as tasks_module

        booking = make_booking(db)
        with patch.object(tasks_module, "SessionLocal", return_value=db), \
             patch.object(tasks_module, "_simulate_external_service", return_value=True), \
             patch.object(tasks_module, "_send_notification_mock") as mock_notify:
            tasks_module.confirm_booking.run(str(booking.id))

        mock_notify.assert_called_once()

    def test_notification_not_sent_on_failure(self, db):
        """При сбое уведомление НЕ отправляется."""
        from app import tasks as tasks_module

        booking = make_booking(db)
        with patch.object(tasks_module, "SessionLocal", return_value=db), \
             patch.object(tasks_module, "_simulate_external_service", return_value=False), \
             patch.object(tasks_module, "_send_notification_mock") as mock_notify:
            tasks_module.confirm_booking.run(str(booking.id))

        mock_notify.assert_not_called()
