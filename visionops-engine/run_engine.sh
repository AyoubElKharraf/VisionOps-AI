#!/bin/sh
set -e

MODE="${ENGINE_MODE:-multi}"
API_URL="${API_URL:-http://backend:8001}"
API_KEY="${VISIONOPS_API_KEY:-visionops-dev-key}"
SOURCE="${VIDEO_SOURCE:-rtsp://mediamtx:8554/cam1}"
CAMERA="${CAMERA_NAME:-demo-camera}"
STREAM_EVERY="${DETECTION_STREAM_EVERY:-1}"
POLL="${CAMERA_POLL_SECONDS:-15}"

if [ "$MODE" = "single" ]; then
  exec python demo_roi.py \
    --skip-benchmark \
    --max-frames 0 \
    --stream-detections \
    --post-alerts \
    --sync-roi \
    --stream-every "$STREAM_EVERY" \
    --api-url "$API_URL" \
    --api-key "$API_KEY" \
    --source "$SOURCE" \
    --camera-name "$CAMERA" \
    --metrics-port 9101
fi

exec python multi_cam_runner.py \
  --api-url "$API_URL" \
  --api-key "$API_KEY" \
  --fallback-source "$SOURCE" \
  --fallback-camera "$CAMERA" \
  --poll-seconds "$POLL" \
  --stream-every "$STREAM_EVERY" \
  --conf "${YOLO_CONF:-0.35}" \
  --max-workers "${ENGINE_MAX_WORKERS:-2}" \
  --metrics-port 9101
