"""Bootstrap demo users when JWT auth is enabled."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import Settings
from app.models import User, UserRole
from app.security import KNOWN_INSECURE_VALUES, is_production

logger = logging.getLogger("visionops-backend")


def ensure_bootstrap_admin(db: Session, settings: Settings) -> None:
    """Create the initial admin account if JWT is configured and no users exist."""
    if not settings.visionops_jwt_secret:
        return
    if db.query(User).count() > 0:
        return

    username = (settings.visionops_admin_username or "admin").strip()
    password = settings.visionops_admin_password or "visionops-admin"
    if len(password) < 8:
        logger.warning("Bootstrap admin password is shorter than 8 characters")
    if is_production(settings) and (
        len(password) < 12 or password.strip().lower() in KNOWN_INSECURE_VALUES
    ):
        raise RuntimeError(
            "Refusing to bootstrap admin with a weak VISIONOPS_ADMIN_PASSWORD in production"
        )

    admin = User(
        username=username,
        password_hash=hash_password(password),
        full_name=settings.visionops_admin_full_name or "VisionOps Admin",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    logger.info("Bootstrap admin user created: %s (change password in production)", username)
