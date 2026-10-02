from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Booking, Payment, WebhookEvent


def create_booking(client, sample):
    response = client.post(
        "/bookings/",
        headers=sample["owner_headers"],
        json={
            "offering_id": sample["offering"].id,
            "appointment_at": (
                datetime.now(timezone.utc) + timedelta(days=2)
            ).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def webhook_headers():
    return {
        "X-Webhook-Secret": settings.webhook_secret.get_secret_value()
    }


def test_signup_login_and_duplicate_email(client):
    payload = {
        "name": "New User",
        "email": "newuser@example.com",
        "password": "TestPassword123!",
    }

    signup = client.post("/auth/signup", json=payload)
    assert signup.status_code == 201, signup.text
    assert signup.json()["is_admin"] is False
    assert "password_hash" not in signup.json()

    duplicate = client.post("/auth/signup", json=payload)
    assert duplicate.status_code == 409

    login = client.post(
        "/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert login.status_code == 200, login.text

    me = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {login.json()['access_token']}"
        },
    )
    assert me.status_code == 200
    assert me.json()["id"] == signup.json()["id"]

    bad_login = client.post(
        "/auth/login",
        json={
            "email": payload["email"],
            "password": "WrongPassword123!",
        },
    )
    assert bad_login.status_code == 401


def test_authentication_and_admin_access(client, sample):
    assert client.get("/bookings/").status_code == 401

    invalid_token = client.get(
        "/bookings/",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert invalid_token.status_code == 401

    forbidden = client.post(
        "/centres",
        headers=sample["owner_headers"],
        json={"name": "Unauthorized Centre", "location": "Delhi"},
    )
    assert forbidden.status_code == 403


def test_booking_price_and_ownership(client, sample):
    booking = create_booking(client, sample)

    assert booking["user_id"] == sample["owner"].id
    assert Decimal(booking["amount"]) == Decimal("450.00")
    assert booking["currency"] == "INR"
    assert booking["status"] == "PENDING"

    other_view = client.get(
        f"/bookings/{booking['id']}",
        headers=sample["other_headers"],
    )
    assert other_view.status_code == 404

    other_payment = client.post(
        "/payments/",
        headers=sample["other_headers"],
        json={"booking_id": booking["id"], "outcome": "SUCCESS"},
    )
    assert other_payment.status_code == 404

    other_list = client.get(
        "/bookings/",
        headers=sample["other_headers"],
    )
    assert other_list.status_code == 200
    assert other_list.json() == []


def test_booking_validation(client, sample):
    future = (
        datetime.now(timezone.utc) + timedelta(days=2)
    ).isoformat()

    past = client.post(
        "/bookings/",
        headers=sample["owner_headers"],
        json={
            "offering_id": sample["offering"].id,
            "appointment_at": (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat(),
        },
    )
    assert past.status_code == 422

    invalid_id = client.post(
        "/bookings/",
        headers=sample["owner_headers"],
        json={"offering_id": 0, "appointment_at": future},
    )
    assert invalid_id.status_code == 422

    missing = client.post(
        "/bookings/",
        headers=sample["owner_headers"],
        json={
            "offering_id": 2147483647,
            "appointment_at": future,
        },
    )
    assert missing.status_code == 404

    supplied_price = client.post(
        "/bookings/",
        headers=sample["owner_headers"],
        json={
            "offering_id": sample["offering"].id,
            "appointment_at": future,
            "amount": "1.00",
        },
    )
    assert supplied_price.status_code == 422


@pytest.mark.parametrize(
    "outcome,booking_status",
    [
        ("SUCCESS", "CONFIRMED"),
        ("FAILED", "FAILED"),
    ],
)
def test_payment_outcomes_and_retries(
    client, sample, db, outcome, booking_status
):
    booking = create_booking(client, sample)
    payload = {"booking_id": booking["id"], "outcome": outcome}

    first = client.post(
        "/payments/",
        headers=sample["owner_headers"],
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == outcome
    assert first.json()["booking_status"] == booking_status

    repeated = client.post(
        "/payments/",
        headers=sample["owner_headers"],
        json=payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]

    count = db.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.booking_id == booking["id"])
    )
    assert count == 1

    opposite = "FAILED" if outcome == "SUCCESS" else "SUCCESS"
    conflict = client.post(
        "/payments/",
        headers=sample["owner_headers"],
        json={"booking_id": booking["id"], "outcome": opposite},
    )
    assert conflict.status_code == 409

    saved_booking = client.get(
        f"/bookings/{booking['id']}",
        headers=sample["owner_headers"],
    )
    assert saved_booking.status_code == 200
    assert saved_booking.json()["status"] == booking_status


@pytest.mark.parametrize(
    "outcome,booking_status",
    [
        ("SUCCESS", "CONFIRMED"),
        ("FAILED", "FAILED"),
    ],
)
def test_webhook_transition_duplicates_and_conflicts(
    client, sample, db, outcome, booking_status
):
    booking = create_booking(client, sample)

    # Seed a pending payment to verify that the webhook itself
    # changes both payment and booking status.
    payment = Payment(
        booking_id=booking["id"],
        amount=Decimal(booking["amount"]),
        currency=booking["currency"],
        status="PENDING",
    )
    db.add(payment)
    db.commit()
    payment_id = payment.id

    payload = {
        "event_id": "evt_test_001",
        "provider_reference": payment.provider_reference,
        "status": outcome,
    }

    unauthorized = client.post("/payments/webhook/", json=payload)
    assert unauthorized.status_code == 401

    first = client.post(
        "/payments/webhook/",
        headers=webhook_headers(),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    assert first.json()["payment"]["status"] == outcome
    assert first.json()["payment"]["booking_status"] == booking_status

    repeated = client.post(
        "/payments/webhook/",
        headers=webhook_headers(),
        json=payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["duplicate"] is True
    assert repeated.json()["payment"]["id"] == payment_id

    opposite = "FAILED" if outcome == "SUCCESS" else "SUCCESS"

    # Reusing an event ID with changed contents must fail.
    changed_event = client.post(
        "/payments/webhook/",
        headers=webhook_headers(),
        json={**payload, "status": opposite},
    )
    assert changed_event.status_code == 409

    # A new event also cannot reverse a completed payment.
    conflicting_event = client.post(
        "/payments/webhook/",
        headers=webhook_headers(),
        json={
            **payload,
            "event_id": "evt_test_002",
            "status": opposite,
        },
    )
    assert conflicting_event.status_code == 409

    db.expire_all()

    assert db.get(Payment, payment_id).status == outcome
    assert db.get(Booking, booking["id"]).status == booking_status

    event_count = db.scalar(
        select(func.count())
        .select_from(WebhookEvent)
        .where(WebhookEvent.payment_id == payment_id)
    )
    assert event_count == 1

