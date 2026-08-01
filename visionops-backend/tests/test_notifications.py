"""Unit tests for alert notification channels — no Postgres/Redis required."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://visionops:visionops_secret@localhost:5434/visionops_db",
)


@pytest.fixture()
def settings_factory(monkeypatch):
    def _apply(**kwargs):
        defaults = {
            "NOTIFY_WEBHOOK_URL": "",
            "NOTIFY_SLACK_WEBHOOK_URL": "",
            "NOTIFY_EMAIL_TO": "",
            "NOTIFY_SMTP_HOST": "",
            "NOTIFY_EVENTS": "created,resolved",
            "NOTIFY_DASHBOARD_BASE_URL": "http://127.0.0.1:3000/alerts",
        }
        defaults.update(kwargs)
        for key, value in defaults.items():
            monkeypatch.setenv(key, str(value))
        from app.config import get_settings

        get_settings.cache_clear()
        return get_settings()

    yield _apply
    from app.config import get_settings

    get_settings.cache_clear()


def test_parse_notify_events_all(settings_factory):
    from app.notifications import parse_notify_events

    settings_factory()
    assert "created" in parse_notify_events("all")
    assert "resolved" in parse_notify_events("created,resolved")
    assert parse_notify_events("created,bogus") == {"created"}


def test_should_notify_requires_channel_and_event(settings_factory):
    from app.notifications import should_notify

    settings_factory(NOTIFY_EVENTS="created", NOTIFY_WEBHOOK_URL="")
    assert should_notify("created") is False

    settings_factory(
        NOTIFY_EVENTS="created,resolved",
        NOTIFY_WEBHOOK_URL="https://hooks.example/visionops",
    )
    assert should_notify("created") is True
    assert should_notify("acknowledged") is False


def test_dispatch_webhook_and_slack(settings_factory):
    from app.notifications import dispatch_channels

    settings = settings_factory(
        NOTIFY_WEBHOOK_URL="https://hooks.example/generic",
        NOTIFY_SLACK_WEBHOOK_URL="https://hooks.example/slack",
        NOTIFY_EMAIL_TO="",
        NOTIFY_SMTP_HOST="",
    )
    payload = {
        "event": "created",
        "event_type": "alert.created",
        "alert_id": "abc",
        "alert_type": "roi_intrusion",
        "incident_status": "open",
        "message": "Intrusion",
        "camera_name": "demo-camera",
        "zone_name": "dock",
        "dashboard_url": "http://127.0.0.1:3000/alerts?highlight=abc",
    }
    with patch("app.notifications._post_json") as post:
        results = dispatch_channels(payload, settings)
    assert results == {"webhook": True, "slack": True}
    assert post.call_count == 2


def test_send_email_uses_smtp(settings_factory):
    from app.notifications import send_email

    settings = settings_factory(
        NOTIFY_EMAIL_TO="ops@example.com",
        NOTIFY_SMTP_HOST="smtp.example.com",
        NOTIFY_SMTP_PORT="587",
        NOTIFY_SMTP_USER="user",
        NOTIFY_SMTP_PASSWORD="secret",
        NOTIFY_SMTP_FROM="visionops@example.com",
        NOTIFY_SMTP_USE_TLS="true",
    )
    payload = {
        "event": "resolved",
        "event_type": "alert.resolved",
        "alert_id": "abc",
        "alert_type": "tripwire",
        "incident_status": "resolved",
        "message": "Cleared",
        "camera_name": "cam1",
        "zone_name": None,
        "actor": "admin",
        "note": "false alarm",
        "dashboard_url": None,
    }
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.notifications.smtplib.SMTP", return_value=smtp) as smtp_cls:
        assert send_email(payload, settings) is True
    smtp_cls.assert_called_once()
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("user", "secret")
    smtp.send_message.assert_called_once()


def test_build_notification_payload(settings_factory):
    from app.notifications import build_notification_payload

    settings_factory()
    alert = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        alert_type=SimpleNamespace(value="roi_intrusion"),
        incident_status="open",
        message="Person in zone",
        zone_name="A",
        class_name="person",
        assigned_to=None,
        camera=SimpleNamespace(name="demo-camera"),
    )
    payload = build_notification_payload(alert, event="created", actor="system")
    assert payload["event_type"] == "alert.created"
    assert payload["camera_name"] == "demo-camera"
    assert "highlight=" in payload["dashboard_url"]


def test_enqueue_skips_when_disabled(settings_factory):
    from app.notifications import enqueue_alert_notification

    settings_factory(NOTIFY_WEBHOOK_URL="", NOTIFY_EVENTS="created")
    alert = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        alert_type=SimpleNamespace(value="roi_intrusion"),
        incident_status="open",
        message="x",
        zone_name=None,
        class_name=None,
        assigned_to=None,
        camera=None,
    )
    assert enqueue_alert_notification(alert, event="created") is False
