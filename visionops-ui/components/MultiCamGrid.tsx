"use client";

import { useMemo } from "react";
import type { Camera } from "@/lib/api";
import { hlsUrlForCamera, whepUrlForCamera } from "@/lib/api";
import { useDetectionsFeed } from "@/lib/useDetectionsFeed";
import { VideoMonitor, type VideoSourceMode } from "@/components/VideoMonitor";

const DEMO_VIDEO =
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4";

type Props = {
  cameras: Camera[];
  mode: VideoSourceMode;
  focusedId?: string | null;
  onFocus: (cameraId: string) => void;
  maxTiles?: number;
};

function gridClass(count: number): string {
  if (count <= 1) return "grid-cols-1";
  if (count === 2) return "grid-cols-1 sm:grid-cols-2";
  if (count <= 4) return "grid-cols-1 sm:grid-cols-2";
  return "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3";
}

export function MultiCamGrid({
  cameras,
  mode,
  focusedId,
  onFocus,
  maxTiles = 9,
}: Props) {
  const { byCamera, wsState } = useDetectionsFeed();
  const tiles = useMemo(() => {
    const active = cameras.filter((c) => c.is_active);
    const list = (active.length ? active : cameras).slice(0, maxTiles);
    return list;
  }, [cameras, maxTiles]);

  if (tiles.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-white/15 px-4 py-6 text-sm text-muted">
        No cameras available for the live grid.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>
          Grid · {tiles.length} camera{tiles.length === 1 ? "" : "s"}
        </span>
        <span
          className={
            wsState === "live"
              ? "text-accent"
              : wsState === "connecting"
                ? "text-amber-300"
                : "text-red-300"
          }
        >
          Shared detections WS: {wsState}
        </span>
        <span className="text-muted">Click a tile to open the full monitor</span>
      </div>
      <div className={`grid gap-3 ${gridClass(tiles.length)}`}>
        {tiles.map((camera) => (
          <div
            key={camera.id}
            className={
              focusedId === camera.id
                ? "rounded-lg ring-2 ring-accent/60"
                : undefined
            }
          >
            <VideoMonitor
              compact
              mode={mode}
              cameraName={camera.name}
              videoSrc={mode === "demo" ? DEMO_VIDEO : undefined}
              hlsUrl={mode === "hls" ? hlsUrlForCamera(camera) : undefined}
              whepUrl={mode === "webrtc" ? whepUrlForCamera(camera) : undefined}
              externalFrame={byCamera[camera.name] ?? null}
              externalWsState={wsState}
              onFocus={() => onFocus(camera.id)}
            />
          </div>
        ))}
      </div>
      {cameras.filter((c) => c.is_active).length > maxTiles && (
        <p className="text-xs text-muted">
          Showing first {maxTiles} active cameras. Focus one for the full overlay
          tools.
        </p>
      )}
    </div>
  );
}
