from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import RecordId


PaymentOutcome = Literal["SUCCESS", "FAILED"]


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: RecordId
    outcome: PaymentOutcome


class PaymentResponse(BaseModel):
    id: int
    booking_id: int
    provider_reference: str
    amount: Decimal
    currency: str
    status: PaymentOutcome
    booking_status: Literal["CONFIRMED", "FAILED"]


class WebhookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    provider_reference: UUID
    status: PaymentOutcome


class WebhookResponse(BaseModel):
    event_id: str
    duplicate: bool
    payment: PaymentResponse

