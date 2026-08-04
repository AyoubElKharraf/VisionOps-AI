"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { ModelArtifact, ModelFormat, ModelRole } from "@/lib/api";
import { visionopsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function ModelRegistry() {
  const { isAdmin, ready } = useAuth();
  const router = useRouter();
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("yolov8n");
  const [version, setVersion] = useState("1.0.0");
  const [role, setRole] = useState<ModelRole>("detector");
  const [format, setFormat] = useState<ModelFormat | "">("");
  const [notes, setNotes] = useState("");
  const [activate, setActivate] = useState(true);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (!ready) return;
    if (!isAdmin) {
      router.replace("/");
    }
  }, [ready, isAdmin, router]);

  const reload = async () => {
    try {
      setLoading(true);
      setModels(await visionopsApi.listModels());
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!ready || !isAdmin) return;
    void reload();
  }, [ready, isAdmin]);

  const upload = async () => {
    if (!file) {
      setStatus("Choose a .onnx or .pt file");
      return;
    }
    if (!name.trim() || !version.trim()) {
      setStatus("Name and version are required");
      return;
    }
    try {
      setBusy(true);
      await visionopsApi.uploadModel({
        file,
        name: name.trim(),
        version: version.trim(),
        role,
        format: format || undefined,
        notes: notes.trim() || undefined,
        activate,
      });
      setFile(null);
      setNotes("");
      setStatus("Model uploaded");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const activateModel = async (id: string) => {
    try {
      setBusy(true);
      await visionopsApi.activateModel(id);
      setStatus("Active model updated — restart the engine (or wait for next container start) to load it");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Activate failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      setBusy(true);
      await visionopsApi.deleteModel(id);
      setStatus("Model deleted");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  if (!ready || !isAdmin) {
    return (
      <p className="text-sm text-muted">Admin access required. Redirecting…</p>
    );
  }

  const byRole = (r: ModelRole) => models.filter((m) => m.role === r);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted">
            Versioned detector and PPE weights stored in MinIO. The engine pulls
            the active version into <code className="text-accent">WEIGHTS_DIR</code>{" "}
            when <code className="text-accent">MODEL_REGISTRY_SYNC</code> is enabled.
          </p>
          <button
            type="button"
            onClick={() => void reload()}
            className="min-h-11 shrink-0 rounded-md border border-white/15 px-3 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        {status && (
          <p className="rounded-md border border-white/10 bg-panel/60 px-3 py-2 text-sm text-accent">
            {status}
          </p>
        )}

        {loading && <p className="text-sm text-muted">Loading models…</p>}

        {(["detector", "ppe"] as ModelRole[]).map((r) => {
          const rows = byRole(r);
          return (
            <section key={r} className="space-y-3">
              <h2 className="font-display text-lg font-semibold capitalize">
                {r}
                <span className="ml-2 text-sm font-normal text-muted">
                  {rows.length} version{rows.length === 1 ? "" : "s"}
                </span>
              </h2>
              {!loading && rows.length === 0 && (
                <p className="rounded-md border border-dashed border-white/15 px-4 py-5 text-sm text-muted">
                  No {r} models yet. Upload weights on the right.
                </p>
              )}
              <div className="space-y-3">
                {rows.map((m) => (
                  <article
                    key={m.id}
                    className="rounded-lg border border-white/10 bg-panel/60 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-display text-base font-semibold">
                          {m.name}
                          <span className="text-muted"> @{m.version}</span>
                        </h3>
                        <p className="mt-1 text-xs text-muted">
                          {m.format} · {m.filename} · {formatBytes(m.size_bytes)}
                          {m.is_active ? (
                            <span className="ml-2 text-accent">active</span>
                          ) : null}
                        </p>
                        {m.notes && (
                          <p className="mt-2 text-sm text-muted">{m.notes}</p>
                        )}
                        <p className="mt-1 font-mono text-[11px] text-muted">
                          sha256 {m.sha256.slice(0, 16)}…
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {!m.is_active && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void activateModel(m.id)}
                            className="min-h-11 rounded-md bg-accent px-3 text-sm font-medium text-black disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                        {!m.is_active && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void remove(m.id)}
                            className="min-h-11 rounded-md border border-white/15 px-3 text-sm hover:bg-white/5 disabled:opacity-50"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      <aside className="h-fit space-y-3 rounded-lg border border-white/10 bg-panel/60 p-4">
        <h2 className="font-display text-lg font-semibold">Upload</h2>
        <label className="block text-sm">
          <span className="text-muted">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Version</span>
          <input
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as ModelRole)}
            className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2"
          >
            <option value="detector">detector</option>
            <option value="ppe">ppe</option>
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-muted">Format (optional)</span>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as ModelFormat | "")}
            className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2"
          >
            <option value="">infer from extension</option>
            <option value="onnx">onnx</option>
            <option value="pytorch">pytorch</option>
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-muted">Notes</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="mt-1 w-full rounded-md border border-white/10 bg-black/30 px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Weights file</span>
          <input
            type="file"
            accept=".onnx,.pt,.pth,.weights,application/octet-stream"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1 w-full text-sm"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={activate}
            onChange={(e) => setActivate(e.target.checked)}
          />
          Activate after upload
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void upload()}
          className="min-h-11 w-full rounded-md bg-accent px-3 text-sm font-medium text-black disabled:opacity-50"
        >
          {busy ? "Working…" : "Upload model"}
        </button>
      </aside>
    </div>
  );
}
