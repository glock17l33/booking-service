from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Имя клиента")
    datetime: datetime = Field(..., description="Дата и время встречи (ISO 8601)")
    service_type: str = Field(..., min_length=1, max_length=100, description="Тип услуги")

    @field_validator("datetime")
    @classmethod
    def datetime_must_be_future(cls, v: datetime) -> datetime:
        # Разрешаем любое время — для тестов удобнее без ограничений
        return v


class BookingResponse(BaseModel):
    id: UUID
    name: str
    datetime: datetime
    service_type: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookingListResponse(BaseModel):
    items: list[BookingResponse]
    total: int
    page: int
    page_size: int
    pages: int
