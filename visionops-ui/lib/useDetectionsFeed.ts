"use client";

import { useEffect, useRef, useState } from "react";
import type { DetectionFrame } from "@/lib/api";
import { detectionsWsUrl } from "@/lib/api";

type WsState = "connecting" | "live" | "offline";

/**
 * Single detections WebSocket fan-out keyed by camera_name.
 * Prefer this in multi-cam layouts to avoid N browser sockets.
 */
export function useDetectionsFeed() {
  const [byCamera, setByCamera] = useState<Record<string, DetectionFrame>>({});
  const [wsState, setWsState] = useState<WsState>("connecting");
  const previousRef = useRef<Record<string, DetectionFrame>>({});

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
            !next.camera_name ||
            !Number.isFinite(next.captured_at_ms) ||
            ageMs <= -1000 ||
            ageMs >= 10_000
          ) {
            return;
          }
          previousRef.current = {
            ...previousRef.current,
            [next.camera_name]: next,
          };
          setByCamera({ ...previousRef.current });
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
  }, []);

  return { byCamera, wsState };
}
