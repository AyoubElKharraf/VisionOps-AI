"""Shared authentication — service API keys and human JWT sessions."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Query, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole

API_KEY_HEADER = "X-API-Key"
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Authenticated caller: human user or machine service key."""

    subject: str
    role: UserRole
    is_service: bool = False
    user_id: uuid.UUID | None = None

    @property
    def is_admin(self) -> bool:
        return self.is_service or self.role == UserRole.admin


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _keys_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def auth_enforced() -> bool:
    settings = get_settings()
    return bool(settings.visionops_api_key or settings.visionops_jwt_secret)


def create_access_token(*, user_id: uuid.UUID, username: str, role: UserRole | str) -> str:
    settings = get_settings()
    if not settings.visionops_jwt_secret:
        raise RuntimeError("VISIONOPS_JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    role_value = role.value if isinstance(role, UserRole) else str(role)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role_value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.visionops_jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.visionops_jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    if not settings.visionops_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT auth is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return jwt.decode(token, settings.visionops_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _service_principal() -> Principal:
    return Principal(subject="service", role=UserRole.admin, is_service=True)


def _user_principal(user: User) -> Principal:
    return Principal(
        subject=user.username,
        role=user.role if isinstance(user.role, UserRole) else UserRole(user.role),
        is_service=False,
        user_id=user.id,
    )


def require_auth(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    api_key: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    """
    Accept service API key or Bearer JWT.
    When neither VISIONOPS_API_KEY nor VISIONOPS_JWT_SECRET is set, auth is open (CI).
    """
    settings = get_settings()
    if not auth_enforced():
        return _service_principal()

    expected_key = settings.visionops_api_key
    if expected_key and _keys_match(x_api_key or api_key, expected_key):
        return _service_principal()

    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        payload = decode_access_token(credentials.credentials)
        try:
            user_id = uuid.UUID(str(payload.get("sub")))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            ) from exc
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User inactive or not found",
            )
        return _user_principal(user)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Backward-compatible alias used by older imports/tests.
require_api_key = require_auth


def require_roles(*roles: UserRole):
    """Restrict a route to the given roles (admins and service keys always pass)."""

    allowed = {UserRole.admin, *roles}

    def _dependency(principal: Annotated[Principal, Depends(require_auth)]) -> Principal:
        if principal.is_service or principal.role in allowed:
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {', '.join(sorted(r.value for r in allowed))}",
        )

    return _dependency


async def accept_websocket_auth(websocket: WebSocket, db: Session) -> Principal:
    """Validate WebSocket clients via ?api_key=, ?token=, or X-API-Key."""
    settings = get_settings()
    if not auth_enforced():
        return _service_principal()

    expected_key = settings.visionops_api_key
    provided_key = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    if expected_key and _keys_match(provided_key, expected_key):
        return _service_principal()

    token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    auth_header = websocket.headers.get("authorization")
    if not token and auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if token and settings.visionops_jwt_secret:
        try:
            payload = jwt.decode(token, settings.visionops_jwt_secret, algorithms=["HS256"])
            user_id = uuid.UUID(str(payload.get("sub")))
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise WebSocketException(code=4401, reason="Invalid or expired token") from exc
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise WebSocketException(code=4401, reason="User inactive or not found")
        return _user_principal(user)

    raise WebSocketException(code=4401, reason="Invalid or missing credentials")


# Backward-compatible alias.
async def accept_websocket_api_key(websocket: WebSocket) -> None:
    settings = get_settings()
    if not auth_enforced():
        return
    expected = settings.visionops_api_key
    provided = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    if expected and _keys_match(provided, expected):
        return
    # Also accept JWT for browser clients when JWT is configured.
    if settings.visionops_jwt_secret:
        token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
        if token:
            try:
                jwt.decode(token, settings.visionops_jwt_secret, algorithms=["HS256"])
                return
            except jwt.PyJWTError:
                pass
    raise WebSocketException(code=4401, reason="Invalid or missing credentials")
