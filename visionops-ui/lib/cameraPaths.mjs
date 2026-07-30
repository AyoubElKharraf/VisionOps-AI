/** Schemes that are not MediaMTX play URLs (engine / demo placeholders). */
const NON_STREAM_SCHEMES = new Set(["stream:", "file:"]);

/** Derive MediaMTX path from RTSP/HLS URL or fall back for demo / name. */
export function streamPathForCamera(camera) {
  try {
    const url = new URL(camera.source_url);
    if (!NON_STREAM_SCHEMES.has(url.protocol)) {
      const part = url.pathname.split("/").filter(Boolean).pop();
      if (part && part !== "index.m3u8") {
        return part.replace(/\.m3u8$/i, "");
      }
    }
  } catch {
    /* ignore invalid URL */
  }
  // Engine placeholders (stream://, file://) → demo MediaMTX path
  if (typeof camera.source_url === "string") {
    const lower = camera.source_url.toLowerCase();
    if (lower.startsWith("stream:") || lower.startsWith("file:")) {
      return "cam1";
    }
  }
  const safe = camera.name
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return safe || "cam1";
}

export function whepUrlForCamera(camera) {
  return `/api/mediamtx/whep?path=${encodeURIComponent(streamPathForCamera(camera))}`;
}

export function hlsUrlForCamera(camera, hlsTemplate = "http://127.0.0.1:8888/cam1/index.m3u8") {
  const path = streamPathForCamera(camera);
  const base = hlsTemplate.replace(/\/[^/]+\/index\.m3u8$/i, "");
  if (base === hlsTemplate) {
    return `http://127.0.0.1:8888/${path}/index.m3u8`;
  }
  return `${base}/${path}/index.m3u8`;
}
