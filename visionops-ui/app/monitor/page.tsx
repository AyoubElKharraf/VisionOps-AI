"use client";

import { useEffect, useState } from "react";
import { VideoMonitor } from "@/components/VideoMonitor";
import { HLS_URL, visionopsApi, type RoiZone } from "@/lib/api";

const DEMO_VIDEO =
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4";

export default function MonitorPage() {
  const [zones, setZones] = useState<RoiZone[]>([]);
  const [useHls, setUseHls] = useState(false);

  useEffect(() => {
    void visionopsApi.listZones().then(setZones).catch(() => setZones([]));
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">Live Monitor</h1>
          <p className="mt-1 text-sm text-muted">
            Canvas overlay synced with engine detections (WebSocket).
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={useHls}
            onChange={(e) => setUseHls(e.target.checked)}
          />
          Prefer MediaMTX HLS
        </label>
      </div>
      <VideoMonitor
        videoSrc={useHls ? undefined : DEMO_VIDEO}
        hlsUrl={useHls ? HLS_URL : undefined}
        zones={zones}
      />
    </div>
  );
}
