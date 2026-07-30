/**
 * Overlay/video synchronization helpers.
 *
 * Detections reach the browser later than the WebRTC frames they describe, so
 * boxes drawn as-is trail the moving object. We estimate a per-track velocity
 * and project each box forward by the residual delay.
 */

export const DEFAULT_VIDEO_LATENCY_MS = 150;
export const MAX_LEAD_MS = 500;

function centerOf(box) {
  return { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
}

/** Per-track velocity in source pixels per millisecond. */
export function trackVelocities(previous, current) {
  const velocities = new Map();
  const deltaMs = (current?.captured_at_ms ?? 0) - (previous?.captured_at_ms ?? 0);
  if (!previous || !current || !(deltaMs > 0)) return velocities;

  const before = new Map();
  for (const box of previous.boxes ?? []) {
    if (box.track_id != null) before.set(box.track_id, box);
  }

  for (const box of current.boxes ?? []) {
    if (box.track_id == null) continue;
    const past = before.get(box.track_id);
    if (!past) continue;
    const from = centerOf(past);
    const to = centerOf(box);
    velocities.set(box.track_id, {
      vx: (to.x - from.x) / deltaMs,
      vy: (to.y - from.y) / deltaMs,
    });
  }
  return velocities;
}

/**
 * How far ahead boxes must be projected: age of the detection minus the
 * video display latency. Negative or excessive values are clamped away.
 */
export function overlayLeadMs(
  nowMs,
  capturedAtMs,
  videoLatencyMs = DEFAULT_VIDEO_LATENCY_MS,
  maxLeadMs = MAX_LEAD_MS,
) {
  const age = nowMs - capturedAtMs;
  if (!Number.isFinite(age)) return 0;
  return Math.min(Math.max(age - videoLatencyMs, 0), maxLeadMs);
}

/** Shift a box along its track velocity, keeping it inside the frame. */
export function extrapolateBox(box, velocity, leadMs, bounds) {
  if (!velocity || !(leadMs > 0)) return box;

  let dx = velocity.vx * leadMs;
  let dy = velocity.vy * leadMs;

  if (bounds?.width > 0) {
    dx = Math.min(Math.max(dx, -box.x1), bounds.width - box.x2);
  }
  if (bounds?.height > 0) {
    dy = Math.min(Math.max(dy, -box.y1), bounds.height - box.y2);
  }

  return {
    ...box,
    x1: box.x1 + dx,
    x2: box.x2 + dx,
    y1: box.y1 + dy,
    y2: box.y2 + dy,
  };
}
