export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";

export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ??
  "ws://127.0.0.1:8001/api/v1/ws/detections";

export const HLS_URL =
  process.env.NEXT_PUBLIC_HLS_URL ?? "http://127.0.0.1:8888/cam1/index.m3u8";

/** Same-origin Next.js proxy → MediaMTX WHEP (avoids CORS). */
export const WHEP_URL =
  process.env.NEXT_PUBLIC_WHEP_URL ?? "/api/mediamtx/whep?path=cam1";

/** WebSocket URL with optional API key query (browsers cannot set X-API-Key). */
export function detectionsWsUrl(base = WS_URL, apiKey = API_KEY): string {
  if (!apiKey) return base;
  try {
    const url = new URL(base);
    url.searchParams.set("api_key", apiKey);
    return url.toString();
  } catch {
    const join = base.includes("?") ? "&" : "?";
    return `${base}${join}api_key=${encodeURIComponent(apiKey)}`;
  }
}

export type Alert = {
  id: string;
  camera_id: string | null;
  alert_type: string;
  status: string;
  zone_name: string | null;
  class_name: string | null;
  track_id: number | null;
  confidence: number | null;
  message: string;
  snapshot_object_key: string | null;
  clip_object_key: string | null;
  snapshot_url: string | null;
  clip_url: string | null;
  created_at: string;
};

export type RoiZone = {
  id: string;
  camera_id: string | null;
  name: string;
  points: number[][];
  color: string;
  max_allowed_objects: number;
  forbidden_classes: string[] | null;
  is_active: boolean;
};

export type DetectionBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
  class_id: number;
  class_name: string;
  track_id?: number | null;
};

export type DetectionFrame = {
  camera_id: string | null;
  camera_name: string;
  frame_index: number;
  captured_at_ms: number;
  sent_at_ms?: number | null;
  received_at_ms?: number | null;
  source_position_ms?: number | null;
  width: number;
  height: number;
  infer_ms?: number | null;
  boxes: DetectionBox[];
  zone_alerts: string[];
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const visionopsApi = {
  health: () => api<{ status: string; phase?: string }>("/health"),
  listAlerts: (limit = 40) => api<Alert[]>(`/api/v1/alerts?limit=${limit}`),
  listZones: (cameraName = "demo-camera") =>
    api<RoiZone[]>(`/api/v1/roi-zones?camera_name=${encodeURIComponent(cameraName)}`),
  createZone: (body: {
    name: string;
    points: number[][];
    color?: string;
    camera_name?: string;
  }) =>
    api<RoiZone>("/api/v1/roi-zones", {
      method: "POST",
      body: JSON.stringify({
        camera_name: "demo-camera",
        max_allowed_objects: 0,
        forbidden_classes: ["person"],
        ...body,
      }),
    }),
  deleteZone: (id: string) =>
    api<void>(`/api/v1/roi-zones/${id}`, { method: "DELETE" }),
  latestDetections: () => api<DetectionFrame>("/api/v1/detections/latest"),
};
