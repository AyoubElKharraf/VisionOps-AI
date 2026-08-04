import {
  hlsUrlForCamera as buildHlsUrl,
  streamPathForCamera as buildStreamPath,
  whepUrlForCamera as buildWhepUrl,
} from "./cameraPaths.mjs";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001";

/** Optional service-key fallback (engine/dev). Prefer JWT from localStorage in the UI. */
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ??
  "ws://127.0.0.1:8001/api/v1/ws/detections";

export const HLS_URL =
  process.env.NEXT_PUBLIC_HLS_URL ?? "http://127.0.0.1:8888/cam1/index.m3u8";

/** Same-origin Next.js proxy → MediaMTX WHEP (avoids CORS). */
export const WHEP_URL =
  process.env.NEXT_PUBLIC_WHEP_URL ?? "/api/mediamtx/whep?path=cam1";

function clientAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("visionops.accessToken");
}

/** WebSocket URL with JWT `token` or API key query (browsers cannot set headers). */
export function detectionsWsUrl(base = WS_URL): string {
  const token = clientAccessToken();
  const credential = token
    ? { key: "token", value: token }
    : API_KEY
      ? { key: "api_key", value: API_KEY }
      : null;
  if (!credential) return base;
  try {
    const url = new URL(base);
    url.searchParams.set(credential.key, credential.value);
    return url.toString();
  } catch {
    const join = base.includes("?") ? "&" : "?";
    return `${base}${join}${credential.key}=${encodeURIComponent(credential.value)}`;
  }
}

/** Derive MediaMTX path from RTSP/HLS URL or fall back to sanitized camera name. */
export function streamPathForCamera(camera: {
  name: string;
  source_url: string;
}): string {
  return buildStreamPath(camera);
}

export function whepUrlForCamera(camera: { name: string; source_url: string }): string {
  return buildWhepUrl(camera);
}

export function hlsUrlForCamera(camera: { name: string; source_url: string }): string {
  return buildHlsUrl(camera, HLS_URL);
}

export type Camera = {
  id: string;
  name: string;
  source_url: string;
  location: string | null;
  is_active: boolean;
  created_at: string;
};

export type AlertEvent = {
  id: string;
  alert_id: string;
  event_type: string;
  actor: string | null;
  message: string;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type Alert = {
  id: string;
  camera_id: string | null;
  camera_name?: string | null;
  alert_type: string;
  status: string;
  incident_status: string;
  zone_name: string | null;
  class_name: string | null;
  track_id: number | null;
  confidence: number | null;
  message: string;
  assigned_to?: string | null;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
  snapshot_object_key: string | null;
  clip_object_key: string | null;
  snapshot_url: string | null;
  clip_url: string | null;
  created_at: string;
  updated_at?: string;
  events?: AlertEvent[];
};

export type RoiZone = {
  id: string;
  camera_id: string | null;
  name: string;
  points: number[][];
  color: string;
  max_allowed_objects: number;
  forbidden_classes: string[] | null;
  loitering_seconds?: number;
  schedule_enabled?: boolean;
  schedule_start?: string;
  schedule_end?: string;
  schedule_days?: number[];
  schedule_timezone?: string;
  require_hardhat?: boolean;
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

export type ZoneOccupancy = {
  zone_name: string;
  count: number;
  max_allowed: number;
  occupancy_pct: number;
  over_capacity: boolean;
  track_ids?: number[];
  loitering_seconds?: number;
  max_dwell_seconds?: number;
  loitering_active?: boolean;
  schedule_active?: boolean;
};

export type HeatmapSnapshot = {
  cols: number;
  rows: number;
  peak: number;
  cells: number[][]; // [col, row, intensity 0..1]
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
  zone_occupancy?: ZoneOccupancy[];
  heatmap?: HeatmapSnapshot | null;
};

export type AuthUserRole = "admin" | "operator";

export type AuthUserProfile = {
  id: string;
  username: string;
  full_name: string | null;
  role: AuthUserRole;
  is_active: boolean;
  created_at: string;
};

export type UserInput = {
  username: string;
  password: string;
  full_name?: string | null;
  role?: AuthUserRole;
  is_active?: boolean;
};

export type CameraInput = {
  name: string;
  source_url: string;
  location?: string | null;
  is_active?: boolean;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const token = clientAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  } else if (API_KEY) {
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
  listCameras: (activeOnly = false) =>
    api<Camera[]>(`/api/v1/cameras${activeOnly ? "?active_only=true" : ""}`),
  createCamera: (body: CameraInput) =>
    api<Camera>("/api/v1/cameras", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateCamera: (id: string, body: Partial<CameraInput>) =>
    api<Camera>(`/api/v1/cameras/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCamera: (id: string) =>
    api<void>(`/api/v1/cameras/${id}`, { method: "DELETE" }),
  listAlerts: (limit = 40, cameraName?: string, incidentStatus?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cameraName) params.set("camera_name", cameraName);
    if (incidentStatus) params.set("incident_status", incidentStatus);
    return api<Alert[]>(`/api/v1/alerts?${params.toString()}`);
  },
  getAlert: (id: string) => api<Alert>(`/api/v1/alerts/${id}`),
  downloadAlertExport: async (id: string) => {
    const headers: Record<string, string> = {};
    const token = clientAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    } else if (API_KEY) {
      headers["X-API-Key"] = API_KEY;
    }
    const res = await fetch(`${API_URL}/api/v1/alerts/${id}/export`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status} ${text}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^"]+)"?/i.exec(disposition);
    a.href = url;
    a.download = match?.[1] || `visionops-incident-${id.slice(0, 8)}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  listAlertEvents: (id: string) => api<AlertEvent[]>(`/api/v1/alerts/${id}/events`),
  acknowledgeAlert: (id: string, body: { actor?: string; note?: string } = {}) =>
    api<Alert>(`/api/v1/alerts/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  assignAlert: (
    id: string,
    body: { assignee: string; actor?: string; note?: string },
  ) =>
    api<Alert>(`/api/v1/alerts/${id}/assign`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resolveAlert: (id: string, body: { actor?: string; note?: string } = {}) =>
    api<Alert>(`/api/v1/alerts/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reopenAlert: (id: string, body: { actor?: string; note?: string } = {}) =>
    api<Alert>(`/api/v1/alerts/${id}/reopen`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  commentAlert: (id: string, body: { message: string; actor?: string }) =>
    api<Alert>(`/api/v1/alerts/${id}/comments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listZones: (cameraName = "demo-camera") =>
    api<RoiZone[]>(`/api/v1/roi-zones?camera_name=${encodeURIComponent(cameraName)}`),
  createZone: (body: {
    name: string;
    points: number[][];
    color?: string;
    camera_name?: string;
    max_allowed_objects?: number;
    forbidden_classes?: string[];
    loitering_seconds?: number;
    schedule_enabled?: boolean;
    schedule_start?: string;
    schedule_end?: string;
    schedule_days?: number[];
    schedule_timezone?: string;
    require_hardhat?: boolean;
  }) =>
    api<RoiZone>("/api/v1/roi-zones", {
      method: "POST",
      body: JSON.stringify({
        ...body,
        max_allowed_objects: body.max_allowed_objects ?? 0,
        forbidden_classes: body.forbidden_classes ?? ["person"],
        loitering_seconds: body.loitering_seconds ?? 0,
        schedule_enabled: body.schedule_enabled ?? false,
        schedule_start: body.schedule_start ?? "00:00",
        schedule_end: body.schedule_end ?? "23:59",
        schedule_days: body.schedule_days ?? [0, 1, 2, 3, 4, 5, 6],
        schedule_timezone: body.schedule_timezone ?? "UTC",
        require_hardhat: body.require_hardhat ?? false,
        camera_name: body.camera_name ?? "demo-camera",
      }),
    }),
  deleteZone: (id: string) =>
    api<void>(`/api/v1/roi-zones/${id}`, { method: "DELETE" }),
  latestDetections: () => api<DetectionFrame>("/api/v1/detections/latest"),
  listUsers: () => api<AuthUserProfile[]>("/api/v1/auth/users"),
  createUser: (body: UserInput) =>
    api<AuthUserProfile>("/api/v1/auth/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
