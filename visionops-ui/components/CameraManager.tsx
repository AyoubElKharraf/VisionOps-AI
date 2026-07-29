"use client";

import { useEffect, useState } from "react";
import type { Camera, CameraInput } from "@/lib/api";
import { streamPathForCamera, visionopsApi } from "@/lib/api";

const emptyForm: CameraInput = {
  name: "",
  source_url: "rtsp://127.0.0.1:8554/cam1",
  location: "",
  is_active: true,
};

export function CameraManager() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [form, setForm] = useState<CameraInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    try {
      setLoading(true);
      setCameras(await visionopsApi.listCameras());
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load cameras");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const reset = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const startEdit = (cam: Camera) => {
    setEditingId(cam.id);
    setForm({
      name: cam.name,
      source_url: cam.source_url,
      location: cam.location ?? "",
      is_active: cam.is_active,
    });
  };

  const save = async () => {
    if (!form.name.trim() || !form.source_url.trim()) {
      setStatus("Name and source URL are required");
      return;
    }
    try {
      const payload: CameraInput = {
        name: form.name.trim(),
        source_url: form.source_url.trim(),
        location: form.location?.trim() || null,
        is_active: form.is_active ?? true,
      };
      if (editingId) {
        await visionopsApi.updateCamera(editingId, payload);
        setStatus("Camera updated");
      } else {
        await visionopsApi.createCamera(payload);
        setStatus("Camera created");
      }
      reset();
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this camera and its ROI zones?")) return;
    try {
      await visionopsApi.deleteCamera(id);
      if (editingId === id) reset();
      setStatus("Camera deleted");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted">
            Cameras drive Monitor overlays, ROI zones, and alert filtering.
          </p>
          <button
            type="button"
            onClick={() => void reload()}
            className="min-h-11 rounded-md border border-white/15 px-3 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        {loading && <p className="text-sm text-muted">Loading cameras…</p>}

        {!loading && cameras.length === 0 && (
          <p className="rounded-md border border-dashed border-white/15 px-4 py-6 text-sm text-muted">
            No cameras yet. Create <code>demo-camera</code> with source{" "}
            <code>rtsp://127.0.0.1:8554/cam1</code> to match the default engine.
          </p>
        )}

        <div className="space-y-3">
          {cameras.map((cam) => (
            <article
              key={cam.id}
              className="rounded-lg border border-white/10 bg-panel/60 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-lg font-semibold">{cam.name}</h2>
                  <p className="mt-1 break-all text-xs text-muted">{cam.source_url}</p>
                  <p className="mt-2 text-xs text-muted">
                    {cam.location || "No location"} · stream path{" "}
                    <code className="text-accent">{streamPathForCamera(cam)}</code>
                    {" · "}
                    <span className={cam.is_active ? "text-accent" : "text-amber-300"}>
                      {cam.is_active ? "active" : "inactive"}
                    </span>
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => startEdit(cam)}
                    className="min-h-11 rounded-md border border-white/15 px-3 text-sm hover:bg-white/5"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(cam.id)}
                    className="min-h-11 rounded-md border border-red-400/30 px-3 text-sm text-red-200 hover:bg-red-500/10"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className="space-y-4 rounded-lg border border-white/10 bg-panel/50 p-4">
        <h2 className="font-display text-lg font-semibold">
          {editingId ? "Edit camera" : "Add camera"}
        </h2>
        <label className="block text-sm">
          Name
          <input
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="demo-camera"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Source URL
          <input
            value={form.source_url}
            onChange={(e) => setForm((f) => ({ ...f, source_url: e.target.value }))}
            placeholder="rtsp://127.0.0.1:8554/cam1"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Location
          <input
            value={form.location ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
            placeholder="Dock A"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_active ?? true}
            onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            className="h-4 w-4 accent-[var(--tw-accent,#3dd6c6)]"
          />
          Active
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void save()}
            className="min-h-11 rounded-md bg-accent px-4 text-sm font-medium text-ink hover:opacity-90"
          >
            {editingId ? "Update" : "Create"}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={reset}
              className="min-h-11 rounded-md border border-white/15 px-4 text-sm hover:bg-white/5"
            >
              Cancel
            </button>
          )}
        </div>
        {status && <p className="text-xs text-accent">{status}</p>}
      </div>
    </div>
  );
}
