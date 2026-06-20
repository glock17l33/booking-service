import uuid
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, Enum, Index, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class BookingStatus(str, PyEnum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    datetime = Column(DateTime(timezone=True), nullable=False)
    service_type = Column(String(100), nullable=False)
    status = Column(
        Enum(BookingStatus),
        nullable=False,
        default=BookingStatus.pending,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_bookings_status_created_at", "status", "created_at"),
    )
