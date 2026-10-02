from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.dependencies import CurrentUser, DbSession
from app.models import Booking, CentreTest
from app.schemas import BookingCreate, BookingResponse


router = APIRouter(prefix="/bookings", tags=["Bookings"])

BookingId = Annotated[int, Path(gt=0, le=2_147_483_647)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=2_147_483_647)]


@router.post(
    "/",
    response_model=BookingResponse,
    status_code=201,
)
def create_booking(
    payload: BookingCreate,
    db: DbSession,
    user: CurrentUser,
):
    # Lock the offering while its availability and price are copied.
    offering = db.scalar(
        select(CentreTest)
        .where(CentreTest.id == payload.offering_id)
        .with_for_update()
    )

    if offering is None:
        raise HTTPException(
            status_code=404,
            detail="Offering not found",
        )

    if not offering.is_active:
        raise HTTPException(
            status_code=409,
            detail="This test offering is currently unavailable",
        )

    booking = Booking(
        user_id=user.id,
        offering_id=offering.id,
        appointment_at=payload.appointment_at,
        amount=offering.price,
        currency=offering.currency,
        status="PENDING",
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking


@router.get("/", response_model=list[BookingResponse])
def list_my_bookings(
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
):
    statement = (
        select(Booking)
        .options(joinedload(Booking.offering))
        .where(Booking.user_id == user.id)
        .order_by(Booking.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return db.scalars(statement).all()


@router.get("/{booking_id}/", response_model=BookingResponse)
def get_my_booking(
    booking_id: BookingId,
    db: DbSession,
    user: CurrentUser,
):
    booking = db.scalar(
        select(Booking)
        .options(joinedload(Booking.offering))
        .where(
            Booking.id == booking_id,
            Booking.user_id == user.id,
        )
    )

    if booking is None:
        raise HTTPException(
            status_code=404,
            detail="Booking not found",
        )

    return booking
