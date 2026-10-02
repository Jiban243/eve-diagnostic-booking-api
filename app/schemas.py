from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


# Authentication schemas

class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class SignupRequest(AuthInput):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class LoginRequest(AuthInput):
    pass


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Shared field types

CatalogueName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=150,
    ),
]

LocationText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
    ),
]

Price = Annotated[
    Decimal,
    Field(gt=0, max_digits=10, decimal_places=2),
]

CurrencyCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z]{3}$"),
]

RecordId = Annotated[
    int,
    Field(gt=0, le=2_147_483_647),
]


# Catalogue schemas

class CatalogueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CentreInput(CatalogueInput):
    name: CatalogueName
    location: LocationText


class CentreResponse(CentreInput):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TestInput(CatalogueInput):
    name: CatalogueName


class TestResponse(TestInput):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OfferingCreate(CatalogueInput):
    test_id: RecordId
    price: Price
    currency: CurrencyCode


class OfferingUpdate(CatalogueInput):
    price: Price
    currency: CurrencyCode
    is_active: bool


class OfferingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    centre_id: int
    test_id: int
    price: Decimal
    currency: str
    is_active: bool


class OfferingListResponse(OfferingResponse):
    test_name: str


# Booking schemas

class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offering_id: RecordId
    appointment_at: AwareDatetime

    @field_validator("appointment_at")
    @classmethod
    def validate_appointment(cls, value: datetime) -> datetime:
        if value <= datetime.now(timezone.utc):
            raise ValueError("Appointment must be in the future")
        return value.astimezone(timezone.utc)


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    offering_id: int
    centre_id: int
    test_id: int
    appointment_at: datetime
    amount: Decimal
    currency: str
    status: Literal["PENDING", "CONFIRMED", "FAILED", "CANCELLED"]
    created_at: datetime

    