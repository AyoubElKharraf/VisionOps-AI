"""Authentication and user-management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    auth_enforced,
    create_access_token,
    hash_password,
    require_auth,
    require_roles,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import AuthStatus, LoginRequest, TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
def auth_status() -> AuthStatus:
    settings = get_settings()
    return AuthStatus(
        auth_enforced=auth_enforced(),
        api_key_enabled=bool(settings.visionops_api_key),
        jwt_enabled=bool(settings.visionops_jwt_secret),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    if not settings.visionops_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT auth is not configured (set VISIONOPS_JWT_SECRET)",
        )

    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenResponse(
        access_token=token,
        expires_in=settings.visionops_jwt_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def me(
    principal=Depends(require_auth),
    db: Session = Depends(get_db),
) -> UserRead:
    if principal.is_service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service API keys have no user profile",
        )
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)


@router.get("/users", response_model=list[UserRead])
def list_users(
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    _: object = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
) -> User:
    username = payload.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail=f"User '{username}' already exists")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
