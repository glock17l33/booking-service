import logging
import random
import uuid

from celery import Task
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.models.booking import Booking, BookingStatus

logger = get_task_logger(__name__)


def _send_notification_mock(booking: Booking) -> None:
    """
    Mock-отправка уведомления клиенту.
    В реальном приложении здесь был бы вызов email/SMS-сервиса.
    """
    logger.info(
        "NOTIFICATION SENT",
        extra={
            "event": "notification_sent",
            "booking_id": str(booking.id),
            "name": booking.name,
            "service_type": booking.service_type,
            "booking_datetime": booking.datetime.isoformat(),
        },
    )


def _simulate_external_service() -> bool:
    """
    Имитация внешнего сервиса.
    Возвращает False (сбой) с вероятностью ~15%.
    """
    return random.random() > 0.15


@celery_app.task(
    bind=True,
    name="app.tasks.confirm_booking",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,          # экспоненциальный backoff
    retry_backoff_max=300,       # максимум 5 минут между попытками
    retry_jitter=True,           # добавляем случайность, чтобы не было thundering herd
    acks_late=True,
)
def confirm_booking(self: Task, booking_id: str) -> dict:
    """
    Celery-задача подтверждения брони.

    Идемпотентность: если бронь уже confirmed/failed — задача завершается
    без изменений. Повторный запуск с тем же booking_id безопасен.
    """
    # Импортируем здесь, чтобы избежать циклических импортов
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        booking = db.query(Booking).filter(Booking.id == uuid.UUID(booking_id)).first()

        if booking is None:
            logger.error(
                "Booking not found",
                extra={"event": "booking_not_found", "booking_id": booking_id},
            )
            return {"status": "error", "reason": "booking_not_found"}

        # --- ИДЕМПОТЕНТНОСТЬ ---
        # Если бронь уже обработана — не делаем ничего
        if booking.status != BookingStatus.pending:
            logger.info(
                "Booking already processed — skipping",
                extra={
                    "event": "task_skipped_idempotent",
                    "booking_id": booking_id,
                    "current_status": booking.status.value,
                },
            )
            return {"status": "skipped", "current_status": booking.status.value}

        # --- ИМИТАЦИЯ ВНЕШНЕГО СЕРВИСА ---
        success = _simulate_external_service()

        if success:
            booking.status = BookingStatus.confirmed
            db.commit()
            _send_notification_mock(booking)
            logger.info(
                "Booking confirmed",
                extra={"event": "booking_confirmed", "booking_id": booking_id},
            )
            return {"status": "confirmed", "booking_id": booking_id}
        else:
            booking.status = BookingStatus.failed
            db.commit()
            logger.warning(
                "Booking failed — external service error",
                extra={"event": "booking_failed", "booking_id": booking_id},
            )
            return {"status": "failed", "booking_id": booking_id}

    except Exception as exc:
        db.rollback()
        logger.error(
            "Unexpected error processing booking",
            extra={"event": "task_error", "booking_id": booking_id, "error": str(exc)},
        )
        raise
    finally:
        db.close()
