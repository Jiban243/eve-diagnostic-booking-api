from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    location: Mapped[str] = mapped_column(String(255))


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))


class CentreTest(Base):
    __tablename__ = "centre_tests"

    __table_args__ = (
        UniqueConstraint(
            "centre_id",
            "test_id",
            name="uq_centre_test",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_centre_test_positive_price",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_centre_test_currency_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    centre_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"),
    )

    test_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_tests.id", ondelete="RESTRICT"),
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
    )


class Booking(Base):
    __tablename__ = "bookings"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_booking_positive_amount",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED')",
            name="ck_booking_status",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_booking_currency_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )

    offering_id: Mapped[int] = mapped_column(
        ForeignKey("centre_tests.id", ondelete="RESTRICT"),
        index=True,
    )

    appointment_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        server_default=text("'PENDING'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    offering: Mapped[CentreTest] = relationship()

    @property
    def centre_id(self) -> int:
        return self.offering.centre_id

    @property
    def test_id(self) -> int:
        return self.offering.test_id


class Payment(Base):
    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_payment_positive_amount",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCESS', 'FAILED')",
            name="ck_payment_status",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_payment_currency_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        unique=True,
    )

    provider_reference: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        default=lambda: str(uuid4()),
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        server_default=text("'PENDING'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILED')",
            name="ck_webhook_event_status",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        index=True,
    )

    status: Mapped[str] = mapped_column(String(20))

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    