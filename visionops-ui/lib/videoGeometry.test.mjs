import assert from "node:assert/strict";
import test from "node:test";

import { objectContainRect, projectVideoPoint } from "./videoGeometry.mjs";

function closeTo(actual, expected, epsilon = 1e-9) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} ≈ ${expected}`);
}

test("centers a 16:9 video inside a square container", () => {
  const rect = objectContainRect(1000, 1000, 1920, 1080);
  closeTo(rect.width, 1000);
  closeTo(rect.height, 562.5);
  closeTo(rect.offsetX, 0);
  closeTo(rect.offsetY, 218.75);
});

test("projects pixel boxes inside the rendered video rectangle", () => {
  const rect = objectContainRect(1000, 1000, 1920, 1080);
  const point = projectVideoPoint(960, 540, rect);
  assert.deepEqual(point, { x: 500, y: 500 });
});

test("projects normalized ROI points inside letterbox offsets", () => {
  const rect = objectContainRect(1000, 1000, 1920, 1080);
  const topLeft = projectVideoPoint(0, 0, rect, true);
  const bottomRight = projectVideoPoint(1, 1, rect, true);
  closeTo(topLeft.x, 0);
  closeTo(topLeft.y, 218.75);
  closeTo(bottomRight.x, 1000);
  closeTo(bottomRight.y, 781.25);
});
