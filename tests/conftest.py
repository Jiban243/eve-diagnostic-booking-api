from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, database_url, get_db
from app.main import app
from app.models import CentreTest, DiagnosticCentre, DiagnosticTest, User
from app.security import create_access_token, hash_password


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        database_url.set(database="eve_test"),
        pool_pre_ping=True,
    )

    if engine.url.database != "eve_test":
        raise RuntimeError("Tests must use eve_test")

    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()


@pytest.fixture
def db(test_engine):
    # Route commits stay inside this outer transaction.
    # Rolling it back removes everything created by each test.
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        )

        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def sample(db):
    owner = User(
        name="Booking Owner",
        email="owner@example.com",
        password_hash=hash_password("TestPassword123!"),
        is_admin=False,
    )
    other = User(
        name="Other User",
        email="other@example.com",
        password_hash=hash_password("TestPassword123!"),
        is_admin=False,
    )
    centre = DiagnosticCentre(
        name="Test Diagnostics",
        location="Delhi",
    )
    diagnostic_test = DiagnosticTest(name="CBC")

    db.add_all([owner, other, centre, diagnostic_test])
    db.flush()

    offering = CentreTest(
        centre_id=centre.id,
        test_id=diagnostic_test.id,
        price=Decimal("450.00"),
        currency="INR",
        is_active=True,
    )
    db.add(offering)
    db.commit()

    return {
        "owner": owner,
        "other": other,
        "offering": offering,
        "owner_headers": {
            "Authorization": f"Bearer {create_access_token(owner.id)}"
        },
        "other_headers": {
            "Authorization": f"Bearer {create_access_token(other.id)}"
        },
    }

