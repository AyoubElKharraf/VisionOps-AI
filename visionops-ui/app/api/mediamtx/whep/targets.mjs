export function mediaMtxBase(configuredBase) {
  const base = new URL(configuredBase);
  if (base.protocol !== "http:" && base.protocol !== "https:") {
    throw new Error("MEDIAMTX_WEBRTC_BASE must use http or https");
  }
  return base;
}

export function whepEndpoint(configuredBase, path) {
  if (!/^[A-Za-z0-9_-][A-Za-z0-9._~-]*$/.test(path) || path === "..") {
    return null;
  }
  const base = mediaMtxBase(configuredBase);
  return new URL(`${path}/whep`, `${base.toString().replace(/\/?$/, "/")}`);
}

export function allowedSessionResource(configuredBase, resource) {
  try {
    const base = mediaMtxBase(configuredBase);
    const target = new URL(resource, base);
    const basePath = base.pathname.replace(/\/$/, "");
    const relativePath = target.pathname.slice(basePath.length);

    if (
      target.origin !== base.origin ||
      !target.pathname.startsWith(`${basePath}/`) ||
      !/^\/[A-Za-z0-9_-][A-Za-z0-9._~-]*\/whep(?:\/|$)/.test(relativePath)
    ) {
      return null;
    }
    return target;
  } catch {
    return null;
  }
}
