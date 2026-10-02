import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.payment_schemas import (
    PaymentRequest,
    PaymentResponse,
    WebhookRequest,
    WebhookResponse,
)
from app.services.payments import process_webhook, simulate_payment


router = APIRouter(prefix="/payments", tags=["Payments"])


def verify_webhook_secret(
    x_webhook_secret: Annotated[
        str | None,
        Header(alias="X-Webhook-Secret"),
    ] = None,
) -> None:
    expected = settings.webhook_secret.get_secret_value()

    if x_webhook_secret is None or not secrets.compare_digest(
        x_webhook_secret.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook credentials",
        )


@router.post("/", response_model=PaymentResponse)
def create_payment(
    payload: PaymentRequest,
    db: DbSession,
    user: CurrentUser,
):
    try:
        result = simulate_payment(
            db=db,
            user_id=user.id,
            booking_id=payload.booking_id,
            outcome=payload.outcome,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post(
    "/webhook/",
    response_model=WebhookResponse,
    dependencies=[Depends(verify_webhook_secret)],
)
def payment_webhook(
    payload: WebhookRequest,
    db: DbSession,
):
    try:
        result = process_webhook(
            db=db,
            event_id=payload.event_id,
            provider_reference=str(payload.provider_reference),
            outcome=payload.status,
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise

