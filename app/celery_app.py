from celery import Celery

from app.config import settings

celery_app = Celery(
    "booking_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    # Сериализация
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Часовой пояс
    timezone="UTC",
    enable_utc=True,
    # Retry-политика: экспоненциальный backoff
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Результаты хранятся 24 часа
    result_expires=86400,
    # Воркер не берёт следующую задачу пока не закончит текущую
    worker_prefetch_multiplier=1,
)
