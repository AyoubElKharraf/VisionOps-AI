"use client";

import { useEffect, useState } from "react";
import { VideoMonitor, type VideoSourceMode } from "@/components/VideoMonitor";
import { HLS_URL, WHEP_URL, visionopsApi, type RoiZone } from "@/lib/api";

const DEMO_VIDEO =
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4";

export default function MonitorPage() {
  const [zones, setZones] = useState<RoiZone[]>([]);
  const [mode, setMode] = useState<VideoSourceMode>("webrtc");

  useEffect(() => {
    void visionopsApi.listZones().then(setZones).catch(() => setZones([]));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Live Monitor</h1>
          <p className="mt-1 text-sm text-muted">
            MediaMTX WebRTC (WHEP) + canvas detections overlay.
          </p>
        </div>
        <label className="flex flex-col gap-1 text-sm text-muted">
          <span>Video source</span>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as VideoSourceMode)}
            className="min-h-11 rounded-md border border-white/15 bg-ink px-3 text-white outline-none focus:border-accent"
          >
            <option value="webrtc">WebRTC · MediaMTX WHEP</option>
            <option value="hls">HLS · MediaMTX</option>
            <option value="demo">Demo MP4 (fallback)</option>
          </select>
        </label>
      </div>

      {mode === "webrtc" && (
        <p className="rounded-md border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-muted">
          Publish first:{" "}
          <code className="text-accent">
            .\scripts\publish-demo-mediamtx.ps1
          </code>{" "}
          then keep this page on WebRTC.
        </p>
      )}

      <VideoMonitor
        mode={mode}
        videoSrc={mode === "demo" ? DEMO_VIDEO : undefined}
        hlsUrl={mode === "hls" ? HLS_URL : undefined}
        whepUrl={WHEP_URL}
        zones={zones}
      />
    </div>
  );
}
