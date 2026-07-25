"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Camera, Hexagon, Bell, Radio } from "lucide-react";
import { visionopsApi } from "@/lib/api";

export default function OverviewPage() {
  const [health, setHealth] = useState<string>("checking…");
  const [alertCount, setAlertCount] = useState<number | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const h = await visionopsApi.health();
        setHealth(`${h.status} · phase ${h.phase ?? "?"}`);
        const alerts = await visionopsApi.listAlerts(100);
        setAlertCount(alerts.length);
      } catch {
        setHealth("offline");
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          VisionOps Control Center
        </h1>
        <p className="mt-2 max-w-2xl text-muted">
          Monitor live detections, draw intrusion zones, and review alert media
          from the async pipeline.
        </p>
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <div className="rounded-md border border-white/10 bg-panel/60 px-4 py-3">
          <p className="text-xs text-muted">API</p>
          <p className="font-medium text-accent">{health}</p>
        </div>
        <div className="rounded-md border border-white/10 bg-panel/60 px-4 py-3">
          <p className="text-xs text-muted">Alerts in DB</p>
          <p className="font-medium">{alertCount ?? "—"}</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          {
            href: "/monitor",
            title: "Live Monitor",
            desc: "Video + canvas bounding boxes via WebSocket",
            icon: Camera,
          },
          {
            href: "/roi",
            title: "ROI Editor",
            desc: "Draw polygonal intrusion zones on camera view",
            icon: Hexagon,
          },
          {
            href: "/alerts",
            title: "Alert Gallery",
            desc: "Snapshots and clips stored on MinIO",
            icon: Bell,
          },
        ].map(({ href, title, desc, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="group rounded-lg border border-white/10 bg-panel/50 p-5 transition hover:border-accent/40 hover:bg-panel/80"
          >
            <Icon className="mb-3 h-5 w-5 text-accent" />
            <h2 className="font-display text-lg font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-muted">{desc}</p>
          </Link>
        ))}
      </div>

      <div className="rounded-lg border border-dashed border-white/15 px-5 py-4 text-sm text-muted">
        <div className="mb-2 flex items-center gap-2 text-accent">
          <Radio className="h-4 w-4" />
          Feed the dashboard
        </div>
        <code className="block whitespace-pre-wrap text-xs leading-relaxed text-white/80">
{`python demo_roi.py --skip-benchmark --max-frames 0 --post-alerts --stream-detections --stream-every 2 --api-url http://127.0.0.1:8001`}
        </code>
      </div>
    </div>
  );
}
