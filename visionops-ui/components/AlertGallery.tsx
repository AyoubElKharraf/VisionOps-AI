"use client";

import { useEffect, useState } from "react";
import type { Alert } from "@/lib/api";
import { visionopsApi } from "@/lib/api";

export function AlertGallery() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setLoading(true);
      setAlerts(await visionopsApi.listAlerts(48));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 8000);
    return () => clearInterval(id);
  }, []);

  if (loading && alerts.length === 0) {
    return <p className="text-sm text-muted">Loading alerts…</p>;
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        {error}
        <button type="button" onClick={() => void load()} className="ml-3 underline">
          Retry
        </button>
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <p className="text-sm text-muted">
        No alerts yet. Run the engine with{" "}
        <code className="text-accent">--post-alerts</code>.
      </p>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {alerts.map((alert) => (
        <article
          key={alert.id}
          className="overflow-hidden rounded-lg border border-white/10 bg-panel/70"
        >
          <div className="aspect-video bg-black/50">
            {alert.snapshot_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={alert.snapshot_url}
                alt={alert.message}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-muted">
                No snapshot
              </div>
            )}
          </div>
          <div className="space-y-2 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs uppercase tracking-wide text-accent">
                {alert.alert_type}
              </span>
              <span className="text-xs text-muted">{alert.status}</span>
            </div>
            <p className="text-sm leading-snug">{alert.message}</p>
            <p className="text-xs text-muted">
              {new Date(alert.created_at).toLocaleString()}
              {alert.zone_name ? ` · ${alert.zone_name}` : ""}
            </p>
            <div className="flex gap-3 text-xs">
              {alert.snapshot_url && (
                <a
                  href={alert.snapshot_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline"
                >
                  Snapshot
                </a>
              )}
              {alert.clip_url && (
                <a
                  href={alert.clip_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline"
                >
                  Clip
                </a>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
