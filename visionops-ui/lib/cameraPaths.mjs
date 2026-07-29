/** Derive MediaMTX path from RTSP/HLS URL or fall back to sanitized camera name. */
export function streamPathForCamera(camera) {
  try {
    const url = new URL(camera.source_url);
    const part = url.pathname.split("/").filter(Boolean).pop();
    if (part && part !== "index.m3u8") {
      return part.replace(/\.m3u8$/i, "");
    }
  } catch {
    /* ignore invalid URL */
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
