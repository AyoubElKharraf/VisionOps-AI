import assert from "node:assert/strict";
import test from "node:test";

import {
  extrapolateBox,
  overlayLeadMs,
  suggestedLatencyMs,
  syncQuality,
  trackVelocities,
} from "./overlaySync.mjs";

const box = (track_id, x1, y1, x2, y2) => ({
  x1,
  y1,
  x2,
  y2,
  confidence: 0.9,
  class_id: 0,
  class_name: "person",
  track_id,
});

test("computes per-track velocity between two frames", () => {
  const velocities = trackVelocities(
    { captured_at_ms: 1000, boxes: [box(1, 0, 0, 10, 20)] },
    { captured_at_ms: 1100, boxes: [box(1, 20, 10, 30, 30)] },
  );
  const v = velocities.get(1);
  assert.equal(v.vx, 0.2);
  assert.equal(v.vy, 0.1);
});

test("ignores untracked boxes and non-monotonic timestamps", () => {
  assert.equal(
    trackVelocities(
      { captured_at_ms: 1000, boxes: [box(null, 0, 0, 10, 10)] },
      { captured_at_ms: 1100, boxes: [box(null, 5, 0, 15, 10)] },
    ).size,
    0,
  );
  assert.equal(
    trackVelocities(
      { captured_at_ms: 1200, boxes: [box(1, 0, 0, 10, 10)] },
      { captured_at_ms: 1100, boxes: [box(1, 5, 0, 15, 10)] },
    ).size,
    0,
  );
});

test("lead time subtracts video latency and clamps to sane range", () => {
  assert.equal(overlayLeadMs(1300, 1000, 150), 150);
  assert.equal(overlayLeadMs(1100, 1000, 150), 0);
  assert.equal(overlayLeadMs(9000, 1000, 150), 500);
  assert.equal(overlayLeadMs(Number.NaN, 1000, 150), 0);
});

test("extrapolates a box forward without leaving the frame", () => {
  const moved = extrapolateBox(box(1, 100, 50, 140, 150), { vx: 0.2, vy: 0 }, 200, {
    width: 640,
    height: 480,
  });
  assert.equal(moved.x1, 140);
  assert.equal(moved.x2, 180);
  assert.equal(moved.y1, 50);

  const clamped = extrapolateBox(box(1, 600, 50, 640, 150), { vx: 1, vy: 0 }, 200, {
    width: 640,
    height: 480,
  });
  assert.equal(clamped.x2, 640);
  assert.equal(clamped.x1, 600);
});

test("returns the original box when velocity or lead is missing", () => {
  const original = box(1, 10, 10, 20, 20);
  assert.equal(extrapolateBox(original, undefined, 200, {}), original);
  assert.equal(extrapolateBox(original, { vx: 1, vy: 1 }, 0, {}), original);
});

test("suggests latency defaults per video mode", () => {
  assert.equal(suggestedLatencyMs("webrtc"), 180);
  assert.equal(suggestedLatencyMs("hls"), 550);
  assert.equal(suggestedLatencyMs("demo"), 80);
  assert.equal(suggestedLatencyMs("unknown", 99), 99);
});

test("classifies overlay sync quality from residual delay", () => {
  assert.equal(syncQuality(150, 150), "synced");
  assert.equal(syncQuality(400, 150), "trailing");
  assert.equal(syncQuality(40, 150), "leading");
  assert.equal(syncQuality(5000, 150), "stale");
});
