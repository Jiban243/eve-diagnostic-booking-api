from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Booking, Payment, WebhookEvent


def payment_result(payment: Payment, booking: Booking) -> dict:
    return {
        "id": payment.id,
        "booking_id": payment.booking_id,
        "provider_reference": payment.provider_reference,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
        "booking_status": booking.status,
    }


def apply_outcome(
    payment: Payment,
    booking: Booking,
    outcome: str,
) -> None:
    if outcome not in {"SUCCESS", "FAILED"}:
        raise HTTPException(status_code=422, detail="Invalid payment outcome")

    if (
        payment.booking_id != booking.id
        or payment.amount != booking.amount
        or payment.currency != booking.currency
    ):
        raise HTTPException(
            status_code=409,
            detail="Payment does not match the booking",
        )

    expected_booking_status = (
        "CONFIRMED" if outcome == "SUCCESS" else "FAILED"
    )

    if payment.status in {"SUCCESS", "FAILED"}:
        if payment.status != outcome:
            raise HTTPException(
                status_code=409,
                detail="A completed payment result cannot be changed",
            )

        if booking.status != expected_booking_status:
            raise HTTPException(
                status_code=409,
                detail="Payment and booking states are inconsistent",
            )

        # The same outcome has already been applied.
        return

    if payment.status != "PENDING" or booking.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail="Booking cannot accept this payment update",
        )

    payment.status = outcome
    booking.status = expected_booking_status


def simulate_payment(
    db: Session,
    user_id: int,
    booking_id: int,
    outcome: str,
) -> dict:
    # Both payment entry points lock the booking before the payment.
    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.user_id == user_id,
        )
        .with_for_update()
    )

    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    payment = db.scalar(
        select(Payment)
        .where(Payment.booking_id == booking.id)
        .with_for_update()
    )

    if payment is None:
        if booking.status != "PENDING":
            raise HTTPException(
                status_code=409,
                detail="Only pending bookings can be paid",
            )

        payment = Payment(
            booking_id=booking.id,
            amount=booking.amount,
            currency=booking.currency,
            status="PENDING",
        )
        db.add(payment)
        db.flush()

    apply_outcome(payment, booking, outcome)
    db.flush()

    return payment_result(payment, booking)


def process_webhook(
    db: Session,
    event_id: str,
    provider_reference: str,
    outcome: str,
) -> dict:
    # Resolve the booking ID without loading a potentially stale payment.
    booking_id = db.scalar(
        select(Payment.booking_id).where(
            Payment.provider_reference == provider_reference
        )
    )

    if booking_id is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .with_for_update()
    )

    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    payment = db.scalar(
        select(Payment)
        .where(Payment.provider_reference == provider_reference)
        .with_for_update()
    )

    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    # The unique event ID handles concurrent duplicate deliveries.
    statement = (
        insert(WebhookEvent)
        .values(
            event_id=event_id,
            payment_id=payment.id,
            status=outcome,
        )
        .on_conflict_do_nothing(
            index_elements=[WebhookEvent.event_id]
        )
        .returning(WebhookEvent.event_id)
    )

    inserted_event_id = db.execute(statement).scalar_one_or_none()
    duplicate = inserted_event_id is None

    if duplicate:
        existing = db.get(WebhookEvent, event_id)

        if (
            existing.payment_id != payment.id
            or existing.status != outcome
        ):
            raise HTTPException(
                status_code=409,
                detail="Event ID was already used with different contents",
            )

    apply_outcome(payment, booking, outcome)
    db.flush()

    return {
        "event_id": event_id,
        "duplicate": duplicate,
        "payment": payment_result(payment, booking),
    }

