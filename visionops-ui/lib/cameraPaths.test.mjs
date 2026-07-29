import assert from "node:assert/strict";
import test from "node:test";

import {
  hlsUrlForCamera,
  streamPathForCamera,
  whepUrlForCamera,
} from "./cameraPaths.mjs";

test("derives MediaMTX path from RTSP source URL", () => {
  assert.equal(
    streamPathForCamera({
      name: "Dock A",
      source_url: "rtsp://127.0.0.1:8554/cam1",
    }),
    "cam1",
  );
});

test("falls back to sanitized camera name", () => {
  assert.equal(
    streamPathForCamera({
      name: "Dock A / North",
      source_url: "file://demo",
    }),
    "Dock-A-North",
  );
});

test("builds WHEP and HLS URLs for a camera", () => {
  const cam = {
    name: "demo-camera",
    source_url: "rtsp://localhost:8554/entrance",
  };
  assert.equal(whepUrlForCamera(cam), "/api/mediamtx/whep?path=entrance");
  assert.equal(
    hlsUrlForCamera(cam),
    "http://127.0.0.1:8888/entrance/index.m3u8",
  );
});
