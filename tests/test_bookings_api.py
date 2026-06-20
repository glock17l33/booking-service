"""
Тесты REST API для /bookings.
Celery-задачи мокируются — тесты не требуют запущенного Redis/Celery.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

BOOKING_PAYLOAD = {
    "name": "Иван Петров",
    "datetime": "2025-12-01T10:00:00Z",
    "service_type": "consultation",
}


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция
# ──────────────────────────────────────────────────────────────────────────────

def create_booking(client, payload=None):
    """Создаёт бронь через API с замокированным Celery."""
    if payload is None:
        payload = BOOKING_PAYLOAD
    with patch("app.routers.bookings.confirm_booking") as mock_task:
        mock_task.apply_async = MagicMock()
        resp = client.post("/bookings", json=payload)
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# POST /bookings
# ──────────────────────────────────────────────────────────────────────────────

class TestCreateBooking:
    def test_create_booking_happy_path(self, client):
        """Успешное создание брони возвращает 201 и статус pending."""
        resp = create_booking(client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["name"] == BOOKING_PAYLOAD["name"]
        assert data["service_type"] == BOOKING_PAYLOAD["service_type"]
        assert "id" in data

    def test_create_booking_returns_uuid(self, client):
        """ID брони — валидный UUID."""
        resp = create_booking(client)
        booking_id = resp.json()["id"]
        uuid.UUID(booking_id)  # не бросает исключение — значит UUID валиден

    def test_create_booking_missing_name(self, client):
        """422 если не передано обязательное поле name."""
        payload = {**BOOKING_PAYLOAD}
        del payload["name"]
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_create_booking_missing_datetime(self, client):
        """422 если не передано поле datetime."""
        payload = {**BOOKING_PAYLOAD}
        del payload["datetime"]
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_create_booking_missing_service_type(self, client):
        """422 если не передан service_type."""
        payload = {**BOOKING_PAYLOAD}
        del payload["service_type"]
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_create_booking_empty_name(self, client):
        """422 если name — пустая строка."""
        payload = {**BOOKING_PAYLOAD, "name": ""}
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_create_booking_invalid_datetime(self, client):
        """422 если datetime — невалидный формат."""
        payload = {**BOOKING_PAYLOAD, "datetime": "not-a-date"}
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# GET /bookings/{id}
# ──────────────────────────────────────────────────────────────────────────────

class TestGetBooking:
    def test_get_booking_happy_path(self, client):
        """Получаем созданную бронь по ID."""
        booking_id = create_booking(client).json()["id"]
        resp = client.get(f"/bookings/{booking_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == booking_id

    def test_get_booking_not_found(self, client):
        """404 для несуществующего UUID."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/bookings/{fake_id}")
        assert resp.status_code == 404

    def test_get_booking_invalid_uuid(self, client):
        """422 для невалидного UUID."""
        resp = client.get("/bookings/not-a-uuid")
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# GET /bookings
# ──────────────────────────────────────────────────────────────────────────────

class TestListBookings:
    def test_list_bookings_empty(self, client):
        """Пустой список при отсутствии броней."""
        resp = client.get("/bookings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_bookings_returns_created(self, client):
        """Созданная бронь появляется в списке."""
        create_booking(client)
        resp = client.get("/bookings")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_bookings_multiple(self, client):
        """Несколько броней — все возвращаются."""
        for _ in range(3):
            create_booking(client)
        resp = client.get("/bookings")
        assert resp.json()["total"] == 3

    def test_list_bookings_filter_by_status(self, client, db_session):
        """Фильтрация по статусу работает корректно."""
        from app.models.booking import Booking, BookingStatus

        # Добавляем бронь напрямую в БД со статусом confirmed
        confirmed = Booking(
            name="Test User",
            datetime=datetime(2025, 12, 1, tzinfo=timezone.utc),
            service_type="consult",
            status=BookingStatus.confirmed,
        )
        db_session.add(confirmed)
        db_session.commit()

        # Создаём pending-бронь через API
        create_booking(client)

        resp_pending = client.get("/bookings?status=pending")
        resp_confirmed = client.get("/bookings?status=confirmed")

        assert resp_pending.json()["total"] == 1
        assert resp_confirmed.json()["total"] == 1

    def test_list_bookings_pagination(self, client):
        """Пагинация — page_size ограничивает количество результатов."""
        for _ in range(5):
            create_booking(client)

        resp = client.get("/bookings?page=1&page_size=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["pages"] == 3

    def test_list_bookings_invalid_status(self, client):
        """422 при неверном значении статуса."""
        resp = client.get("/bookings?status=unknown_status")
        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /bookings/{id}
# ──────────────────────────────────────────────────────────────────────────────

class TestDeleteBooking:
    def test_delete_pending_booking(self, client):
        """Удаление pending-брони возвращает 204."""
        booking_id = create_booking(client).json()["id"]
        resp = client.delete(f"/bookings/{booking_id}")
        assert resp.status_code == 204

    def test_delete_booking_removes_from_db(self, client):
        """После удаления GET возвращает 404."""
        booking_id = create_booking(client).json()["id"]
        client.delete(f"/bookings/{booking_id}")
        resp = client.get(f"/bookings/{booking_id}")
        assert resp.status_code == 404

    def test_delete_confirmed_booking_returns_409(self, client, db_session):
        """Нельзя удалить confirmed-бронь — 409 Conflict."""
        from app.models.booking import Booking, BookingStatus

        booking = Booking(
            name="Test",
            datetime=datetime(2025, 12, 1, tzinfo=timezone.utc),
            service_type="consult",
            status=BookingStatus.confirmed,
        )
        db_session.add(booking)
        db_session.commit()

        resp = client.delete(f"/bookings/{booking.id}")
        assert resp.status_code == 409

    def test_delete_failed_booking_returns_409(self, client, db_session):
        """Нельзя удалить failed-бронь — 409 Conflict."""
        from app.models.booking import Booking, BookingStatus

        booking = Booking(
            name="Test",
            datetime=datetime(2025, 12, 1, tzinfo=timezone.utc),
            service_type="consult",
            status=BookingStatus.failed,
        )
        db_session.add(booking)
        db_session.commit()

        resp = client.delete(f"/bookings/{booking.id}")
        assert resp.status_code == 409

    def test_delete_not_found(self, client):
        """404 при удалении несуществующей брони."""
        resp = client.delete(f"/bookings/{uuid.uuid4()}")
        assert resp.status_code == 404
