"""SQLAlchemy engine / session."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_alert_workflow_columns() -> None:
    """Add incident-lifecycle columns on existing Postgres volumes (no Alembic yet)."""
    statements = [
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS incident_status VARCHAR(32) NOT NULL DEFAULT 'open'",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(120)",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR(120)",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(120)",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolution_note TEXT",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def init_db() -> None:
    # Import models so metadata is registered
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        _ensure_alert_workflow_columns()
    except Exception:
        # SQLite or fresh DBs may not need this; create_all already applied schema.
        pass
