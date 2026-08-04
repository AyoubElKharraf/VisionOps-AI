"use client";

import { useEffect, useRef, useState } from "react";
import type { RoiZone } from "@/lib/api";
import { visionopsApi } from "@/lib/api";

type Point = [number, number];

export function RoiEditor({
  imageUrl = "/demo-poster.svg",
  cameraName = "demo-camera",
}: {
  imageUrl?: string;
  cameraName?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [zones, setZones] = useState<RoiZone[]>([]);
  const [name, setName] = useState("zone_restreinte");
  const [mode, setMode] = useState<"intrusion" | "occupancy" | "loitering">(
    "intrusion",
  );
  const [capacity, setCapacity] = useState(5);
  const [loiterSeconds, setLoiterSeconds] = useState(15);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleStart, setScheduleStart] = useState("22:00");
  const [scheduleEnd, setScheduleEnd] = useState("06:00");
  const [scheduleDays, setScheduleDays] = useState<number[]>([
    0, 1, 2, 3, 4, 5, 6,
  ]);
  const [status, setStatus] = useState<string>("");
  const [size, setSize] = useState({ w: 640, h: 360 });

  const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

  const toggleDay = (day: number) => {
    setScheduleDays((prev) => {
      if (prev.includes(day)) {
        const next = prev.filter((d) => d !== day);
        return next.length ? next : prev;
      }
      return [...prev, day].sort((a, b) => a - b);
    });
  };

  const reload = async () => {
    try {
      setZones(await visionopsApi.listZones(cameraName));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load zones");
    }
  };

  useEffect(() => {
    setPoints([]);
    void reload();
  }, [cameraName]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.src = imageUrl;
    img.onload = () => {
      const maxW = canvas.parentElement?.clientWidth || 800;
      const scale = Math.min(1, maxW / img.width);
      const w = Math.floor(img.width * scale);
      const h = Math.floor(img.height * scale);
      canvas.width = w;
      canvas.height = h;
      setSize({ w, h });
      redraw(ctx, img, w, h, points, zones);
    };

    const onResize = () => {
      if (img.complete) {
        const maxW = canvas.parentElement?.clientWidth || 800;
        const scale = Math.min(1, maxW / img.width);
        const w = Math.floor(img.width * scale);
        const h = Math.floor(img.height * scale);
        canvas.width = w;
        canvas.height = h;
        setSize({ w, h });
        redraw(ctx, img, w, h, points, zones);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [imageUrl, points, zones]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((e.clientY - rect.top) / rect.height) * canvas.height;
    setPoints((prev) => [...prev, [x, y]]);
  };

  const save = async () => {
    if (points.length < 3) {
      setStatus("Need at least 3 points");
      return;
    }
    try {
      // Store normalized 0-1 coords for resolution independence
      const normalized = points.map(
        ([x, y]) => [x / size.w, y / size.h] as number[],
      );
      const zoneColor =
        mode === "occupancy" ? "#f59e0b" : mode === "loitering" ? "#a78bfa" : "#ef4444";
      await visionopsApi.createZone({
        name,
        points: normalized,
        color: zoneColor,
        camera_name: cameraName,
        max_allowed_objects: mode === "occupancy" ? Math.max(1, capacity) : 0,
        forbidden_classes:
          mode === "occupancy" || mode === "loitering" ? [] : ["person"],
        loitering_seconds:
          mode === "loitering" ? Math.max(1, loiterSeconds) : 0,
        schedule_enabled: scheduleEnabled,
        schedule_start: scheduleStart,
        schedule_end: scheduleEnd,
        schedule_days: scheduleDays,
        schedule_timezone: "UTC",
      });
      setPoints([]);
      setStatus("Zone saved");
      await reload();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Save failed");
    }
  };

  const remove = async (id: string) => {
    await visionopsApi.deleteZone(id);
    await reload();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div>
        <p className="mb-3 text-sm text-muted">
          Camera <code className="text-accent">{cameraName}</code> — click the
          image to place polygon vertices. Save when done (≥ 3 points).
        </p>
        <canvas
          ref={canvasRef}
          onClick={onClick}
          className="w-full cursor-crosshair rounded-lg border border-white/10 bg-black/40"
        />
      </div>
      <div className="space-y-4">
        <label className="block text-sm">
          Zone name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Rule mode
          <select
            value={mode}
            onChange={(e) => {
              const value = e.target.value;
              if (value === "occupancy" || value === "loitering") setMode(value);
              else setMode("intrusion");
            }}
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          >
            <option value="intrusion">Intrusion (any person)</option>
            <option value="occupancy">Occupancy (capacity)</option>
            <option value="loitering">Loitering (dwell time)</option>
          </select>
        </label>
        {mode === "occupancy" && (
          <label className="block text-sm">
            Capacity (max people)
            <input
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(Math.max(1, Number(e.target.value) || 1))}
              className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
            />
          </label>
        )}
        {mode === "loitering" && (
          <label className="block text-sm">
            Dwell threshold (seconds)
            <input
              type="number"
              min={1}
              value={loiterSeconds}
              onChange={(e) =>
                setLoiterSeconds(Math.max(1, Number(e.target.value) || 1))
              }
              className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
            />
          </label>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={scheduleEnabled}
            onChange={(e) => setScheduleEnabled(e.target.checked)}
            className="rounded border-white/20"
          />
          Limit rules to a schedule
        </label>
        {scheduleEnabled && (
          <div className="space-y-3 rounded-md border border-white/10 p-3">
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-xs text-muted">
                Start (UTC)
                <input
                  type="time"
                  value={scheduleStart}
                  onChange={(e) => setScheduleStart(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/10 bg-ink px-2 py-1.5 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-muted">
                End (UTC)
                <input
                  type="time"
                  value={scheduleEnd}
                  onChange={(e) => setScheduleEnd(e.target.value)}
                  className="mt-1 w-full rounded-md border border-white/10 bg-ink px-2 py-1.5 text-sm text-white"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-1">
              {DAY_LABELS.map((label, day) => {
                const on = scheduleDays.includes(day);
                return (
                  <button
                    key={label}
                    type="button"
                    onClick={() => toggleDay(day)}
                    className={
                      on
                        ? "rounded px-2 py-1 text-xs bg-accent text-ink"
                        : "rounded px-2 py-1 text-xs border border-white/15 text-muted"
                    }
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted">
              Overnight windows supported (e.g. 22:00 → 06:00). Days: Mon=0.
            </p>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setPoints([])}
            className="min-h-11 rounded-md border border-white/15 px-4 text-sm hover:bg-white/5"
          >
            Clear points
          </button>
          <button
            type="button"
            onClick={() => void save()}
            className="min-h-11 rounded-md bg-accent px-4 text-sm font-medium text-ink hover:opacity-90"
          >
            Save ROI
          </button>
        </div>
        <p className="text-xs text-muted">Draft points: {points.length}</p>
        {status && <p className="text-xs text-accent">{status}</p>}
        <div className="space-y-2">
          <p className="text-sm font-medium">Saved zones</p>
          {zones.length === 0 && (
            <p className="text-xs text-muted">No zones yet</p>
          )}
          {zones.map((z) => (
            <div
              key={z.id}
              className="flex items-center justify-between rounded-md border border-white/10 px-3 py-2 text-sm"
            >
              <span>
                {z.name}
                <span className="ml-2 text-xs text-muted">
                  {(z.loitering_seconds ?? 0) > 0
                    ? `loiter ${z.loitering_seconds}s`
                    : z.max_allowed_objects > 0
                      ? `cap ${z.max_allowed_objects}`
                      : "intrusion"}
                  {z.schedule_enabled
                    ? ` · ${z.schedule_start}-${z.schedule_end}`
                    : ""}
                </span>
              </span>
              <button
                type="button"
                onClick={() => void remove(z.id)}
                className="text-xs text-red-300 hover:underline"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function redraw(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  w: number,
  h: number,
  draft: Point[],
  zones: RoiZone[],
) {
  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);

  for (const zone of zones) {
    drawPoly(
      ctx,
      zone.points.map(([x, y]) =>
        x <= 1 && y <= 1 ? ([x * w, y * h] as Point) : ([x, y] as Point),
      ),
      zone.color || "#ef4444",
      0.25,
    );
  }

  if (draft.length) {
    drawPoly(ctx, draft, "#3dd6c6", 0.2);
    for (const [x, y] of draft) {
      ctx.fillStyle = "#3dd6c6";
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function drawPoly(
  ctx: CanvasRenderingContext2D,
  pts: Point[],
  color: string,
  alpha: number,
) {
  if (pts.length < 2) return;
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
  if (pts.length >= 3) ctx.closePath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
  if (pts.length >= 3) {
    ctx.fillStyle = hexAlpha(color, alpha);
    ctx.fill();
  }
}

function hexAlpha(hex: string, alpha: number) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}
