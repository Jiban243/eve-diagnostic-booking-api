from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import AdminUser, DbSession
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest
from app.schemas import (
    CentreInput,
    CentreResponse,
    OfferingCreate,
    OfferingListResponse,
    OfferingResponse,
    OfferingUpdate,
    TestInput,
    TestResponse,
)


router = APIRouter(tags=["Diagnostic Catalogue"])

PathId = Annotated[int, Path(gt=0, le=2_147_483_647)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=2_147_483_647)]


def get_or_404(db, model, record_id, label):
    record = db.get(model, record_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"{label} not found",
        )

    return record


@router.post("/centres/", response_model=CentreResponse, status_code=201)
def create_centre(payload: CentreInput, db: DbSession, admin: AdminUser):
    centre = DiagnosticCentre(**payload.model_dump())
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre


@router.get("/centres/", response_model=list[CentreResponse])
def list_centres(
    db: DbSession,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
):
    statement = (
        select(DiagnosticCentre)
        .order_by(DiagnosticCentre.id)
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(statement).all()


@router.get("/centres/{centre_id}/", response_model=CentreResponse)
def get_centre(centre_id: PathId, db: DbSession):
    return get_or_404(db, DiagnosticCentre, centre_id, "Centre")


@router.put("/centres/{centre_id}/", response_model=CentreResponse)
def update_centre(
    centre_id: PathId,
    payload: CentreInput,
    db: DbSession,
    admin: AdminUser,
):
    centre = get_or_404(db, DiagnosticCentre, centre_id, "Centre")
    centre.name = payload.name
    centre.location = payload.location
    db.commit()
    db.refresh(centre)
    return centre


@router.post("/tests/", response_model=TestResponse, status_code=201)
def create_test(payload: TestInput, db: DbSession, admin: AdminUser):
    test = DiagnosticTest(**payload.model_dump())
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.get("/tests/", response_model=list[TestResponse])
def list_tests(
    db: DbSession,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
):
    statement = (
        select(DiagnosticTest)
        .order_by(DiagnosticTest.id)
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(statement).all()


@router.put("/tests/{test_id}/", response_model=TestResponse)
def update_test(
    test_id: PathId,
    payload: TestInput,
    db: DbSession,
    admin: AdminUser,
):
    test = get_or_404(db, DiagnosticTest, test_id, "Test")
    test.name = payload.name
    db.commit()
    db.refresh(test)
    return test


@router.post(
    "/centres/{centre_id}/tests/",
    response_model=OfferingResponse,
    status_code=201,
)
def create_offering(
    centre_id: PathId,
    payload: OfferingCreate,
    db: DbSession,
    admin: AdminUser,
):
    get_or_404(db, DiagnosticCentre, centre_id, "Centre")
    get_or_404(db, DiagnosticTest, payload.test_id, "Test")

    offering = CentreTest(
        centre_id=centre_id,
        **payload.model_dump(),
    )
    db.add(offering)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail="This test is already listed at this centre",
            ) from exc

        raise

    db.refresh(offering)
    return offering


@router.get(
    "/centres/{centre_id}/tests/",
    response_model=list[OfferingListResponse],
)
def list_centre_tests(
    centre_id: PathId,
    db: DbSession,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
):
    get_or_404(db, DiagnosticCentre, centre_id, "Centre")

    statement = (
        select(
            CentreTest.id,
            CentreTest.centre_id,
            CentreTest.test_id,
            CentreTest.price,
            CentreTest.currency,
            CentreTest.is_active,
            DiagnosticTest.name.label("test_name"),
        )
        .join(
            DiagnosticTest,
            DiagnosticTest.id == CentreTest.test_id,
        )
        .where(
            CentreTest.centre_id == centre_id,
            CentreTest.is_active.is_(True),
        )
        .order_by(CentreTest.id)
        .offset(offset)
        .limit(limit)
    )

    return db.execute(statement).mappings().all()


@router.put(
    "/centres/{centre_id}/tests/{offering_id}/",
    response_model=OfferingResponse,
)
def update_offering(
    centre_id: PathId,
    offering_id: PathId,
    payload: OfferingUpdate,
    db: DbSession,
    admin: AdminUser,
):
    offering = db.scalar(
        select(CentreTest).where(
            CentreTest.id == offering_id,
            CentreTest.centre_id == centre_id,
        )
    )

    if offering is None:
        raise HTTPException(status_code=404, detail="Offering not found")

    offering.price = payload.price
    offering.currency = payload.currency
    offering.is_active = payload.is_active

    db.commit()
    db.refresh(offering)
    return offering

