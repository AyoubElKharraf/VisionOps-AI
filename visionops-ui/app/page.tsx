"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Boxes, Camera, Hexagon, Radio } from "lucide-react";
import { visionopsApi, type Alert } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function countByStatus(alerts: Alert[]) {
  let open = 0;
  let acked = 0;
  let resolved = 0;
  for (const a of alerts) {
    if (a.incident_status === "resolved") resolved += 1;
    else if (a.incident_status === "acknowledged") acked += 1;
    else open += 1;
  }
  return { open, acked, resolved, total: alerts.length };
}

export default function OverviewPage() {
  const { isAdmin, ready } = useAuth();
  const [health, setHealth] = useState<string>("checking…");
  const [cameraCount, setCameraCount] = useState<number | null>(null);
  const [stats, setStats] = useState<ReturnType<typeof countByStatus> | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [h, alerts, cameras] = await Promise.all([
          visionopsApi.health(),
          visionopsApi.listAlerts(100),
          visionopsApi.listCameras(true),
        ]);
        if (cancelled) return;
        setHealth(`${h.status} · phase ${h.phase ?? "?"}`);
        setStats(countByStatus(alerts));
        setCameraCount(cameras.length);
      } catch {
        if (!cancelled) setHealth("offline");
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const tiles = [
    {
      href: "/cameras",
      title: "Cameras",
      desc: "Register sources and MediaMTX stream paths",
      icon: Radio,
    },
    {
      href: "/monitor",
      title: "Live Monitor",
      desc: "Video + synced detection overlay",
      icon: Camera,
    },
    {
      href: "/roi",
      title: "ROI Editor",
      desc: "Intrusion, occupancy, loitering, PPE zones",
      icon: Hexagon,
    },
    {
      href: "/alerts",
      title: "Alert Gallery",
      desc: stats
        ? `${stats.open} open · triage snapshots & clips`
        : "Snapshots, clips, and incident triage",
      icon: Bell,
    },
    ...(ready && isAdmin
      ? [
          {
            href: "/models",
            title: "Models",
            desc: "Upload and activate detector / PPE weights",
            icon: Boxes,
          },
        ]
      : []),
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          VisionOps Control Center
        </h1>
        <p className="mt-2 max-w-2xl text-muted">
          Monitor live detections, draw spatial rules, and triage incidents from
          one place.
        </p>
      </div>

      <div className="flex flex-wrap gap-3 text-sm">
        <div className="rounded-md border border-white/10 bg-panel/60 px-4 py-3">
          <p className="text-xs text-muted">API</p>
          <p className="font-medium text-accent">{health}</p>
        </div>
        <div className="rounded-md border border-white/10 bg-panel/60 px-4 py-3">
          <p className="text-xs text-muted">Active cameras</p>
          <p className="font-medium">{cameraCount ?? "—"}</p>
        </div>
        <Link
          href="/alerts"
          className="rounded-md border border-white/10 bg-panel/60 px-4 py-3 transition hover:border-accent/40"
        >
          <p className="text-xs text-muted">Open incidents</p>
          <p className="font-medium text-red-300">{stats?.open ?? "—"}</p>
        </Link>
        <div className="rounded-md border border-white/10 bg-panel/60 px-4 py-3">
          <p className="text-xs text-muted">Acked / resolved</p>
          <p className="font-medium">
            {stats ? `${stats.acked} / ${stats.resolved}` : "—"}
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {tiles.map(({ href, title, desc, icon: Icon }) => (
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
