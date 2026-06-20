import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.schemas.booking import BookingCreate, BookingListResponse, BookingResponse

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать бронь",
)
def create_booking(
    payload: BookingCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> BookingResponse:
    """
    Создаёт новую бронь со статусом **pending** и ставит задачу в очередь Celery.
    """
    # Импортируем здесь, чтобы задача была доступна
    from app.tasks import confirm_booking

    booking = Booking(
        name=payload.name,
        datetime=payload.datetime,
        service_type=payload.service_type,
        status=BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Отправляем задачу в Celery (асинхронно)
    confirm_booking.apply_async(
        args=[str(booking.id)],
        task_id=f"confirm-{booking.id}",  # детерминированный task_id для идемпотентности
    )

    return booking  # type: ignore[return-value]


@router.get(
    "",
    response_model=BookingListResponse,
    summary="Список броней",
)
def list_bookings(
    status_filter: Optional[BookingStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=1, le=100, description="Размер страницы"),
    db: Session = Depends(get_db),
) -> BookingListResponse:
    """
    Возвращает список броней с опциональным фильтром по статусу и пагинацией.
    """
    query = db.query(Booking)

    if status_filter is not None:
        query = query.filter(Booking.status == status_filter)

    total = query.count()
    pages = math.ceil(total / page_size) if total > 0 else 1

    items = (
        query.order_by(Booking.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return BookingListResponse(
        items=items,  # type: ignore[arg-type]
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Получить бронь по ID",
)
def get_booking(booking_id: UUID, db: Session = Depends(get_db)) -> BookingResponse:
    """
    Возвращает бронь по UUID. Статус: **pending** / **confirmed** / **failed**.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )
    return booking  # type: ignore[return-value]


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить бронь",
)
def delete_booking(booking_id: UUID, db: Session = Depends(get_db)) -> None:
    """
    Отменяет бронь. Разрешено только для статуса **pending**.
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel booking with status '{booking.status.value}'. Only 'pending' bookings can be cancelled.",
        )
    db.delete(booking)
    db.commit()
