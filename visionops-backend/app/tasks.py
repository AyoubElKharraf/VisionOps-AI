"""Celery tasks — snapshot / clip processing for alerts."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from uuid import UUID

import cv2

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.minio_client import upload_bytes, upload_file
from app.models import Alert, AlertStatus
from app.notifications import dispatch_channels

logger = logging.getLogger("visionops.tasks")


def _extract_clip(
    source_path: str,
    frame_index: int | None,
    out_path: Path,
    pre_s: float,
    post_s: float,
) -> bool:
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        logger.error("Cannot open source video: %s", source_path)
        return False

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)

    center = frame_index if frame_index is not None else max(0, total // 2)
    start = max(0, int(center - pre_s * fps))
    end = min(total - 1, int(center + post_s * fps)) if total > 0 else int(center + post_s * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, max(fps, 1.0), (width, height))
    if not writer.isOpened():
        cap.release()
        return False

    idx = start
    while idx <= end:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(frame)
        idx += 1

    writer.release()
    cap.release()
    return out_path.exists() and out_path.stat().st_size > 0


@celery_app.task(name="visionops.process_alert_media", bind=True, max_retries=2)
def process_alert_media(self, alert_id: str, snapshot_b64: str | None = None) -> dict:
    """Upload snapshot (+ optional clip) for an alert to MinIO."""
    import base64

    settings = get_settings()
    db = SessionLocal()
    try:
        alert = db.get(Alert, UUID(alert_id))
        if alert is None:
            return {"ok": False, "error": "alert_not_found"}

        alert.status = AlertStatus.processing
        db.commit()

        prefix = f"alerts/{alert_id}"

        if snapshot_b64:
            raw = base64.b64decode(snapshot_b64)
            key = f"{prefix}/snapshot.jpg"
            upload_bytes(key, raw, "image/jpeg")
            alert.snapshot_object_key = key
            logger.info("Uploaded snapshot %s (%d bytes)", key, len(raw))

        if alert.source_video_path and Path(alert.source_video_path).exists():
            with tempfile.TemporaryDirectory(prefix="visionops_clip_") as tmp:
                clip_path = Path(tmp) / "clip.mp4"
                ok = _extract_clip(
                    alert.source_video_path,
                    alert.frame_index,
                    clip_path,
                    settings.alert_clip_pre_seconds,
                    settings.alert_clip_post_seconds,
                )
                if ok:
                    key = f"{prefix}/clip.mp4"
                    upload_file(key, str(clip_path), "video/mp4")
                    alert.clip_object_key = key
                    logger.info("Uploaded clip %s", key)
                else:
                    logger.warning("Clip extraction failed for alert %s", alert_id)

        alert.status = AlertStatus.ready
        alert.error_message = None
        db.commit()
        return {
            "ok": True,
            "alert_id": alert_id,
            "snapshot_object_key": alert.snapshot_object_key,
            "clip_object_key": alert.clip_object_key,
            "status": alert.status.value,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("process_alert_media failed: %s", exc)
        try:
            alert = db.get(Alert, UUID(alert_id))
            if alert is not None:
                alert.status = AlertStatus.failed
                alert.error_message = str(exc)[:1000]
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise self.retry(exc=exc, countdown=5)
    finally:
        db.close()


@celery_app.task(name="visionops.dispatch_alert_notification", bind=True, max_retries=2)
def dispatch_alert_notification(self, payload: dict) -> dict:
    """Deliver alert notification to configured webhook / Slack / email channels."""
    try:
        results = dispatch_channels(payload)
        logger.info(
            "Notification dispatched event=%s alert=%s results=%s",
            payload.get("event"),
            payload.get("alert_id"),
            results,
        )
        return {"ok": True, "results": results, "alert_id": payload.get("alert_id")}
    except Exception as exc:  # noqa: BLE001
        logger.exception("dispatch_alert_notification failed: %s", exc)
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(name="visionops.ping")
def ping() -> str:
    return "pong"
