"use client";

import { useEffect, useState } from "react";
import type { Alert, AlertEvent } from "@/lib/api";
import { visionopsApi } from "@/lib/api";

const INCIDENT_FILTERS = [
  { value: "", label: "All incidents" },
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
] as const;

function statusTone(incidentStatus: string): string {
  if (incidentStatus === "resolved") return "text-accent";
  if (incidentStatus === "acknowledged") return "text-amber-300";
  return "text-red-300";
}

function AlertCard({
  alert,
  actor,
  onChanged,
}: {
  alert: Alert;
  actor: string;
  onChanged: () => Promise<void>;
}) {
  const [assignee, setAssignee] = useState(alert.assigned_to ?? "");
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [events, setEvents] = useState<AlertEvent[]>(alert.events ?? []);
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<Alert>) => {
    try {
      setBusy(true);
      setError(null);
      const updated = await action();
      setEvents(updated.events ?? []);
      setAssignee(updated.assigned_to ?? "");
      setNote("");
      setComment("");
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = async () => {
    try {
      setShowHistory(true);
      setEvents(await visionopsApi.listAlertEvents(alert.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
    }
  };

  return (
    <article className="overflow-hidden rounded-lg border border-white/10 bg-panel/70">
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
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs uppercase tracking-wide text-accent">
            {alert.alert_type}
          </span>
          <div className="text-right text-xs">
            <p className={statusTone(alert.incident_status)}>
              {alert.incident_status}
            </p>
            <p className="text-muted">media: {alert.status}</p>
          </div>
        </div>
        <p className="text-sm leading-snug">{alert.message}</p>
        <p className="text-xs text-muted">
          {new Date(alert.created_at).toLocaleString()}
          {alert.camera_name ? ` · ${alert.camera_name}` : ""}
          {alert.zone_name ? ` · ${alert.zone_name}` : ""}
          {alert.assigned_to ? ` · assigned ${alert.assigned_to}` : ""}
        </p>
        {alert.resolution_note && (
          <p className="text-xs text-accent">Resolution: {alert.resolution_note}</p>
        )}

        <div className="flex flex-wrap gap-2 text-xs">
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

        <div className="space-y-2 border-t border-white/10 pt-3">
          <label className="block text-xs text-muted">
            Assignee
            <input
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="operator name"
              className="mt-1 w-full rounded-md border border-white/10 bg-ink px-2 py-1.5 text-sm text-white outline-none focus:border-accent"
            />
          </label>
          <label className="block text-xs text-muted">
            Note
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="optional note"
              className="mt-1 w-full rounded-md border border-white/10 bg-ink px-2 py-1.5 text-sm text-white outline-none focus:border-accent"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {alert.incident_status !== "resolved" && (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      visionopsApi.acknowledgeAlert(alert.id, {
                        actor,
                        note: note || undefined,
                      }),
                    )
                  }
                  className="min-h-9 rounded-md border border-white/15 px-3 text-xs hover:bg-white/5 disabled:opacity-50"
                >
                  Acknowledge
                </button>
                <button
                  type="button"
                  disabled={busy || !assignee.trim()}
                  onClick={() =>
                    void run(() =>
                      visionopsApi.assignAlert(alert.id, {
                        assignee: assignee.trim(),
                        actor,
                        note: note || undefined,
                      }),
                    )
                  }
                  className="min-h-9 rounded-md border border-white/15 px-3 text-xs hover:bg-white/5 disabled:opacity-50"
                >
                  Assign
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(() =>
                      visionopsApi.resolveAlert(alert.id, {
                        actor,
                        note: note || undefined,
                      }),
                    )
                  }
                  className="min-h-9 rounded-md bg-accent px-3 text-xs font-medium text-ink hover:opacity-90 disabled:opacity-50"
                >
                  Resolve
                </button>
              </>
            )}
            {alert.incident_status === "resolved" && (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    visionopsApi.reopenAlert(alert.id, {
                      actor,
                      note: note || undefined,
                    }),
                  )
                }
                className="min-h-9 rounded-md border border-amber-400/30 px-3 text-xs text-amber-100 hover:bg-amber-500/10 disabled:opacity-50"
              >
                Reopen
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Add a comment"
              className="min-h-9 flex-1 rounded-md border border-white/10 bg-ink px-2 text-sm text-white outline-none focus:border-accent"
            />
            <button
              type="button"
              disabled={busy || !comment.trim()}
              onClick={() =>
                void run(() =>
                  visionopsApi.commentAlert(alert.id, {
                    message: comment.trim(),
                    actor,
                  }),
                )
              }
              className="min-h-9 rounded-md border border-white/15 px-3 text-xs hover:bg-white/5 disabled:opacity-50"
            >
              Comment
            </button>
          </div>
          <button
            type="button"
            onClick={() => void loadHistory()}
            className="text-xs text-accent hover:underline"
          >
            {showHistory ? "Refresh history" : "Show history"}
          </button>
          {showHistory && (
            <ul className="max-h-40 space-y-1 overflow-y-auto text-xs text-muted">
              {events.length === 0 && <li>No events yet</li>}
              {events.map((event) => (
                <li key={event.id} className="rounded border border-white/5 px-2 py-1">
                  <span className="text-accent">{event.event_type}</span>
                  {event.actor ? ` · ${event.actor}` : ""}
                  {" · "}
                  {new Date(event.created_at).toLocaleString()}
                  <p className="text-white/80">{event.message}</p>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="text-xs text-red-300">{error}</p>}
        </div>
      </div>
    </article>
  );
}

export function AlertGallery({ cameraName }: { cameraName?: string }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidentFilter, setIncidentFilter] = useState("");
  const [actor, setActor] = useState("operator");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setLoading(true);
      setAlerts(
        await visionopsApi.listAlerts(48, cameraName, incidentFilter || undefined),
      );
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 10000);
    return () => clearInterval(id);
  }, [cameraName, incidentFilter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-muted">
          <span>Incident status</span>
          <select
            value={incidentFilter}
            onChange={(e) => setIncidentFilter(e.target.value)}
            className="min-h-11 rounded-md border border-white/15 bg-ink px-3 text-white outline-none focus:border-accent"
          >
            {INCIDENT_FILTERS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-muted">
          <span>Acting as</span>
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            className="min-h-11 rounded-md border border-white/15 bg-ink px-3 text-white outline-none focus:border-accent"
          />
        </label>
        <button
          type="button"
          onClick={() => void load()}
          className="min-h-11 rounded-md border border-white/15 px-4 text-sm hover:bg-white/5"
        >
          Refresh
        </button>
      </div>

      {loading && alerts.length === 0 && (
        <p className="text-sm text-muted">Loading alerts…</p>
      )}

      {error && (
        <div className="rounded-md border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
          <button type="button" onClick={() => void load()} className="ml-3 underline">
            Retry
          </button>
        </div>
      )}

      {!loading && !error && alerts.length === 0 && (
        <p className="text-sm text-muted">
          No alerts for <code className="text-accent">{cameraName ?? "this camera"}</code>
          {incidentFilter ? ` with status ${incidentFilter}` : ""}.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {alerts.map((alert) => (
          <AlertCard
            key={`${alert.id}-${alert.updated_at ?? alert.incident_status}`}
            alert={alert}
            actor={actor.trim() || "operator"}
            onChanged={load}
          />
        ))}
      </div>
    </div>
  );
}
