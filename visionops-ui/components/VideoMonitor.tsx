"use client";

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import type { DetectionFrame, RoiZone } from "@/lib/api";
import { detectionsWsUrl } from "@/lib/api";
import { objectContainRect, projectVideoPoint } from "@/lib/videoGeometry.mjs";
import {
  DEFAULT_VIDEO_LATENCY_MS,
  extrapolateBox,
  overlayLeadMs,
  trackVelocities,
} from "@/lib/overlaySync.mjs";
import { startWhepPlayback, type WhepSession } from "@/lib/whep";

export type VideoSourceMode = "webrtc" | "hls" | "demo";

type TrackVelocity = { vx: number; vy: number };

const LATENCY_STORAGE_KEY = "visionops:videoLatencyMs";

type Props = {
  mode?: VideoSourceMode;
  videoSrc?: string;
  hlsUrl?: string;
  whepUrl?: string;
  zones?: RoiZone[];
  cameraName?: string;
  className?: string;
};

export function VideoMonitor({
  mode = "webrtc",
  videoSrc,
  hlsUrl,
  whepUrl = "/api/mediamtx/whep?path=cam1",
  zones = [],
  cameraName = "demo-camera",
  className,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [frame, setFrame] = useState<DetectionFrame | null>(null);
  const [wsState, setWsState] = useState<"connecting" | "live" | "offline">("connecting");
  const [videoError, setVideoError] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<"idle" | "connecting" | "live" | "error">(
    "idle",
  );
  const [videoLatencyMs, setVideoLatencyMs] = useState(DEFAULT_VIDEO_LATENCY_MS);
  const [leadMs, setLeadMs] = useState(0);
  const velocitiesRef = useRef<Map<number, TrackVelocity>>(new Map());
  const previousFrameRef = useRef<DetectionFrame | null>(null);

  useEffect(() => {
    const stored = Number(window.localStorage.getItem(LATENCY_STORAGE_KEY));
    if (Number.isFinite(stored) && stored >= 0) setVideoLatencyMs(stored);
  }, []);

  const changeVideoLatency = (value: number) => {
    setVideoLatencyMs(value);
    window.localStorage.setItem(LATENCY_STORAGE_KEY, String(value));
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    setVideoError(null);
    setStreamState("connecting");
    let hls: Hls | null = null;
    let whep: WhepSession | null = null;
    let cancelled = false;

    const run = async () => {
      video.pause();
      video.removeAttribute("src");
      video.srcObject = null;
      video.load();

      if (mode === "webrtc") {
        try {
          whep = await startWhepPlayback(whepUrl, video);
          if (cancelled) {
            await whep.close();
            return;
          }
          setStreamState("live");
        } catch (err) {
          if (cancelled) return;
          setStreamState("error");
          setVideoError(
            err instanceof Error
              ? `WebRTC/WHEP: ${err.message} — publish a stream to MediaMTX (cam1) or switch mode`
              : "WebRTC failed",
          );
        }
        return;
      }

      if (mode === "hls" && hlsUrl) {
        if (Hls.isSupported()) {
          hls = new Hls({ enableWorker: true, lowLatencyMode: true });
          hls.loadSource(hlsUrl);
          hls.attachMedia(video);
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (!cancelled) setStreamState("live");
          });
          hls.on(Hls.Events.ERROR, () => {
            if (!cancelled) {
              setStreamState("error");
              setVideoError("HLS unavailable — is MediaMTX publishing /cam1 ?");
            }
          });
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
          video.src = hlsUrl;
          setStreamState("live");
        }
        return;
      }

      if (videoSrc) {
        video.loop = true;
        video.src = videoSrc;
        void video.play().catch(() => undefined);
        setStreamState("live");
      }
    };

    void run();

    return () => {
      cancelled = true;
      hls?.destroy();
      void whep?.close();
      video.srcObject = null;
    };
  }, [mode, hlsUrl, videoSrc, whepUrl]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (closed) return;
      setWsState("connecting");
      ws = new WebSocket(detectionsWsUrl());
      ws.onopen = () => setWsState("live");
      ws.onmessage = (ev) => {
        try {
          const next = JSON.parse(ev.data) as DetectionFrame;
          const ageMs = Date.now() - next.captured_at_ms;
          if (
            next.camera_name === cameraName &&
            Number.isFinite(next.captured_at_ms) &&
            ageMs > -1000 &&
            ageMs < 10_000
          ) {
            velocitiesRef.current = trackVelocities(previousFrameRef.current, next);
            previousFrameRef.current = next;
            setFrame(next);
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        setWsState("offline");
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [cameraName]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    const video = videoRef.current;
    if (!canvas || !wrap) return;

    const draw = () => {
      const rect = wrap.getBoundingClientRect();
      const w = Math.max(1, Math.floor(rect.width));
      const h = Math.max(1, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      const srcW = frame?.width || video?.videoWidth || w;
      const srcH = frame?.height || video?.videoHeight || h;
      const videoRect = objectContainRect(w, h, srcW, srcH);

      for (const zone of zones) {
        if (!zone.points?.length) continue;
        ctx.beginPath();
        zone.points.forEach(([x, y], i) => {
          const normalized = x >= 0 && x <= 1 && y >= 0 && y <= 1;
          const point = projectVideoPoint(x, y, videoRect, normalized);
          if (i === 0) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        });
        ctx.closePath();
        ctx.fillStyle = "rgba(239, 68, 68, 0.18)";
        ctx.strokeStyle = zone.color || "#ef4444";
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();
      }

      if (frame?.boxes?.length) {
        const lead = overlayLeadMs(Date.now(), frame.captured_at_ms, videoLatencyMs);
        setLeadMs(Math.round(lead));
        for (const raw of frame.boxes) {
          const box = extrapolateBox(
            raw,
            raw.track_id != null ? velocitiesRef.current.get(raw.track_id) : undefined,
            lead,
            { width: srcW, height: srcH },
          );
          const topLeft = projectVideoPoint(box.x1, box.y1, videoRect);
          const bottomRight = projectVideoPoint(box.x2, box.y2, videoRect);
          const { x: x1, y: y1 } = topLeft;
          const { x: x2, y: y2 } = bottomRight;
          ctx.strokeStyle = "#3dd6c6";
          ctx.lineWidth = 2;
          ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
          const label = `${box.class_name} ${(box.confidence * 100).toFixed(0)}%`;
          ctx.font = "12px Segoe UI, sans-serif";
          const tw = ctx.measureText(label).width + 8;
          ctx.fillStyle = "#3dd6c6";
          ctx.fillRect(x1, Math.max(0, y1 - 18), tw, 18);
          ctx.fillStyle = "#0b1220";
          ctx.fillText(label, x1 + 4, Math.max(12, y1 - 5));
        }
      }

      if (frame?.zone_alerts?.length) {
        ctx.fillStyle = "rgba(239, 68, 68, 0.9)";
        ctx.font = "bold 14px Segoe UI, sans-serif";
        ctx.fillText(frame.zone_alerts[0], 12, 28);
      }
    };

    let animationFrame = 0;
    const render = () => {
      draw();
      animationFrame = window.requestAnimationFrame(render);
    };
    animationFrame = window.requestAnimationFrame(render);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [frame, zones, videoLatencyMs]);

  return (
    <div className={className}>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <span
          className={
            streamState === "live"
              ? "text-accent"
              : streamState === "connecting"
                ? "text-amber-300"
                : streamState === "error"
                  ? "text-red-300"
                  : "text-muted"
          }
        >
          Video ({mode}): {streamState}
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
          Detections WS: {wsState}
        </span>
        {frame?.infer_ms != null && (
          <span className="text-muted">infer {frame.infer_ms.toFixed(1)} ms</span>
        )}
        {frame && (
          <span className="text-muted">
            boxes {frame.boxes.length} · frame {frame.frame_index}
          </span>
        )}
        {frame?.received_at_ms != null && (
          <span className="text-muted">
            transport {Math.max(0, frame.received_at_ms - frame.captured_at_ms)} ms
          </span>
        )}
        {videoError && <span className="max-w-xl text-amber-300">{videoError}</span>}
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-muted">
        <label className="flex items-center gap-2">
          <span>Video latency</span>
          <input
            type="range"
            min={0}
            max={600}
            step={10}
            value={videoLatencyMs}
            onChange={(e) => changeVideoLatency(Number(e.target.value))}
            className="h-1 w-40 accent-accent"
          />
          <span className="w-14 text-white">{videoLatencyMs} ms</span>
        </label>
        <span>
          overlay lead {leadMs} ms — raise the slider if boxes run ahead, lower it if
          they trail
        </span>
      </div>
      <div
        ref={wrapRef}
        className="relative aspect-video overflow-hidden rounded-lg border border-white/10 bg-black/60"
      >
        <video
          ref={videoRef}
          className="absolute inset-0 h-full w-full object-contain"
          muted
          playsInline
          autoPlay
          controls={mode !== "webrtc"}
        />
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
        />
      </div>
    </div>
  );
}
