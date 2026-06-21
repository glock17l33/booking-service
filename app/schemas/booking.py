"""Pydantic-схемы для бронирования."""

from datetime import datetime as dt
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    """Схема создания брони."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Имя клиента",
    )
    datetime: dt = Field(..., description="Дата и время встречи (ISO 8601)")
    service_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Тип услуги",
    )

    @field_validator("datetime")
    @classmethod
    def datetime_must_be_future(cls, v: dt) -> dt:
        """Валидация даты (placeholder для проверки на будущее время)."""
        return v


class BookingResponse(BaseModel):
    """Схема ответа с данными брони."""

    id: UUID
    name: str
    booking_datetime: dt = Field(serialization_alias="datetime")
    service_type: str
    status: BookingStatus
    created_at: dt
    updated_at: dt

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "by_alias": True,
    }


class BookingListResponse(BaseModel):
    """Схема ответа со списком броней и пагинацией."""

    items: list[BookingResponse]
    total: int
    page: int
    page_size: int
    pages: int
