"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { VideoMonitor, type VideoSourceMode } from "@/components/VideoMonitor";
import { CameraSelect } from "@/components/CameraSelect";
import {
  HLS_URL,
  WHEP_URL,
  hlsUrlForCamera,
  visionopsApi,
  whepUrlForCamera,
  type RoiZone,
} from "@/lib/api";
import { useSelectedCamera } from "@/lib/useSelectedCamera";

const DEMO_VIDEO =
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4";

export default function MonitorPage() {
  const { cameras, selected, selectedId, selectCamera, loading, error } =
    useSelectedCamera();
  const [zones, setZones] = useState<RoiZone[]>([]);
  const [mode, setMode] = useState<VideoSourceMode>("webrtc");

  useEffect(() => {
    if (!selected) {
      setZones([]);
      return;
    }
    void visionopsApi
      .listZones(selected.name)
      .then(setZones)
      .catch(() => setZones([]));
  }, [selected]);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Live Monitor</h1>
          <p className="mt-1 text-sm text-muted">
            MediaMTX WebRTC (WHEP) + canvas detections overlay. Tune video latency
            per source so boxes stay locked to motion.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <CameraSelect
            cameras={cameras}
            selectedId={selectedId}
            onChange={selectCamera}
            loading={loading}
          />
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
      </div>

      {error && (
        <p className="rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      )}

      {!loading && !selected && (
        <p className="rounded-md border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          No camera selected.{" "}
          <Link href="/cameras" className="text-accent underline">
            Create a camera
          </Link>{" "}
          first.
        </p>
      )}

      {mode === "webrtc" && selected && (
        <p className="rounded-md border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-muted">
          Publish stream path matching this camera, then keep WebRTC selected.
          Engine:{" "}
          <code className="text-accent">
            --camera-name {selected.name}
          </code>
        </p>
      )}

      {selected && (
        <VideoMonitor
          mode={mode}
          videoSrc={mode === "demo" ? DEMO_VIDEO : undefined}
          hlsUrl={mode === "hls" ? hlsUrlForCamera(selected) : HLS_URL}
          whepUrl={mode === "webrtc" ? whepUrlForCamera(selected) : WHEP_URL}
          zones={zones}
          cameraName={selected.name}
        />
      )}
    </div>
  );
}
