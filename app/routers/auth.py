from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import CurrentUser, DbSession
from app.models import User
from app.schemas import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(payload: SignupRequest, db: DbSession):
    user = User(
        name=payload.name,
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        is_admin=False,
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc

        raise

    db.refresh(user)
    return user


@router.post("/login/", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession):
    user = db.scalar(
        select(User).where(User.email == str(payload.email))
    )

    stored_hash = user.password_hash if user else DUMMY_HASH
    password_valid = verify_password(payload.password, stored_hash)

    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id)
    )


@router.get("/me/", response_model=UserResponse)
def get_me(user: CurrentUser):
    return user

