"""Alembic configuration smoke tests — no database required."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def test_alembic_heads_include_initial_revision():
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert {
        "0001_initial_schema",
        "0002_users_auth",
        "0003_roi_loitering",
        "0004_roi_schedule",
        "0005_roi_ppe",
        "0006_model_registry",
    }.issubset(revisions)
    assert script.get_heads() == ["0006_model_registry"]


def test_run_migrations_helper_is_importable():
    from app.database import init_db, run_migrations

    assert callable(run_migrations)
    assert callable(init_db)
