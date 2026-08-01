"""Alert notification dispatch — webhook, Slack, and SMTP email."""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings, get_settings
from app.models import Alert

logger = logging.getLogger("visionops.notifications")

SUPPORTED_EVENTS = frozenset(
    {
        "created",
        "acknowledged",
        "assigned",
        "resolved",
        "reopened",
        "commented",
    }
)


def parse_notify_events(raw: str) -> set[str]:
    value = (raw or "").strip().lower()
    if not value:
        return set()
    if value == "all":
        return set(SUPPORTED_EVENTS)
    return {part.strip() for part in value.split(",") if part.strip() in SUPPORTED_EVENTS}


def channels_enabled(settings: Settings | None = None) -> dict[str, bool]:
    s = settings or get_settings()
    return {
        "webhook": bool(s.notify_webhook_url.strip()),
        "slack": bool(s.notify_slack_webhook_url.strip()),
        "email": bool(s.notify_email_to.strip() and s.notify_smtp_host.strip()),
    }


def any_channel_enabled(settings: Settings | None = None) -> bool:
    return any(channels_enabled(settings).values())


def should_notify(event: str, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return event in parse_notify_events(s.notify_events) and any_channel_enabled(s)


def build_notification_payload(
    alert: Alert,
    *,
    event: str,
    actor: str | None = None,
    note: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    alert_id = str(alert.id)
    camera_name = alert.camera.name if getattr(alert, "camera", None) else None
    alert_type = (
        alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type)
    )
    dashboard = (s.notify_dashboard_base_url or "").rstrip("/")
    link = f"{dashboard}?highlight={alert_id}" if dashboard else None
    return {
        "event": event,
        "event_type": f"alert.{event}",
        "alert_id": alert_id,
        "alert_type": alert_type,
        "incident_status": alert.incident_status,
        "message": alert.message,
        "camera_name": camera_name,
        "zone_name": alert.zone_name,
        "class_name": alert.class_name,
        "assigned_to": alert.assigned_to,
        "actor": actor,
        "note": note,
        "dashboard_url": link,
    }


def _post_json(url: str, body: dict[str, Any], *, timeout: float = 8.0) -> None:
    data = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "VisionOps-Notify/1.0"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL from operator config
        resp.read()


def send_webhook(payload: dict[str, Any], settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    url = s.notify_webhook_url.strip()
    if not url:
        return False
    try:
        _post_json(url, payload)
        return True
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Webhook notify failed: %s", exc)
        return False


def send_slack(payload: dict[str, Any], settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    url = s.notify_slack_webhook_url.strip()
    if not url:
        return False
    title = f"VisionOps · {payload.get('event_type', 'alert')}"
    lines = [
        f"*{title}*",
        f"• Type: `{payload.get('alert_type')}` · Status: `{payload.get('incident_status')}`",
        f"• Camera: {payload.get('camera_name') or '—'} · Zone: {payload.get('zone_name') or '—'}",
        f"• {payload.get('message') or '(no message)'}",
    ]
    if payload.get("actor"):
        lines.append(f"• Actor: {payload['actor']}")
    if payload.get("note"):
        lines.append(f"• Note: {payload['note']}")
    if payload.get("dashboard_url"):
        lines.append(f"<{payload['dashboard_url']}|Open in dashboard>")
    body = {"text": "\n".join(lines)}
    try:
        _post_json(url, body)
        return True
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Slack notify failed: %s", exc)
        return False


def send_email(payload: dict[str, Any], settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    recipients = [addr.strip() for addr in s.notify_email_to.split(",") if addr.strip()]
    host = s.notify_smtp_host.strip()
    if not recipients or not host:
        return False

    subject = (
        f"[VisionOps] {payload.get('event_type')} · "
        f"{payload.get('alert_type')} · {payload.get('camera_name') or 'camera'}"
    )
    body_lines = [
        f"Event: {payload.get('event_type')}",
        f"Alert ID: {payload.get('alert_id')}",
        f"Type: {payload.get('alert_type')}",
        f"Status: {payload.get('incident_status')}",
        f"Camera: {payload.get('camera_name') or '—'}",
        f"Zone: {payload.get('zone_name') or '—'}",
        f"Message: {payload.get('message') or '—'}",
    ]
    if payload.get("actor"):
        body_lines.append(f"Actor: {payload['actor']}")
    if payload.get("note"):
        body_lines.append(f"Note: {payload['note']}")
    if payload.get("dashboard_url"):
        body_lines.append(f"Dashboard: {payload['dashboard_url']}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s.notify_smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content("\n".join(body_lines))

    try:
        if s.notify_smtp_use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, s.notify_smtp_port, timeout=10) as smtp:
                smtp.starttls(context=context)
                if s.notify_smtp_user:
                    smtp.login(s.notify_smtp_user, s.notify_smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, s.notify_smtp_port, timeout=10) as smtp:
                if s.notify_smtp_user:
                    smtp.login(s.notify_smtp_user, s.notify_smtp_password)
                smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email notify failed: %s", exc)
        return False


def dispatch_channels(payload: dict[str, Any], settings: Settings | None = None) -> dict[str, bool]:
    s = settings or get_settings()
    results: dict[str, bool] = {}
    enabled = channels_enabled(s)
    if enabled["webhook"]:
        results["webhook"] = send_webhook(payload, s)
    if enabled["slack"]:
        results["slack"] = send_slack(payload, s)
    if enabled["email"]:
        results["email"] = send_email(payload, s)
    return results


def enqueue_alert_notification(
    alert: Alert,
    *,
    event: str,
    actor: str | None = None,
    note: str | None = None,
) -> bool:
    """Queue Celery notification if configured. Returns True when a task was enqueued."""
    settings = get_settings()
    if not should_notify(event, settings):
        return False
    payload = build_notification_payload(
        alert, event=event, actor=actor, note=note, settings=settings
    )
    try:
        from app.tasks import dispatch_alert_notification

        dispatch_alert_notification.delay(payload)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not enqueue notification (%s); sending inline: %s", event, exc)
        dispatch_channels(payload, settings)
        return True
