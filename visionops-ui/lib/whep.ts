/**
 * WHEP client for MediaMTX WebRTC playback (browser).
 * Signaling can go through a same-origin Next.js proxy to avoid CORS.
 */

export type WhepSession = {
  pc: RTCPeerConnection;
  resourceUrl: string | null;
  close: () => Promise<void>;
};

function waitIceGatheringComplete(pc: RTCPeerConnection, timeoutMs = 4000): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(), timeoutMs);
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        window.clearTimeout(timer);
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}

export async function startWhepPlayback(
  whepUrl: string,
  video: HTMLVideoElement,
  options?: {
    iceServers?: RTCIceServer[];
  },
): Promise<WhepSession> {
  const pc = new RTCPeerConnection({
    iceServers: options?.iceServers ?? [{ urls: "stun:stun.l.google.com:19302" }],
  });

  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });

  pc.ontrack = (ev) => {
    if (ev.streams[0]) {
      video.srcObject = ev.streams[0];
      void video.play().catch(() => {
        /* autoplay may require muted — already muted in UI */
      });
    } else {
      const stream = new MediaStream([ev.track]);
      video.srcObject = stream;
      void video.play().catch(() => undefined);
    }
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await waitIceGatheringComplete(pc);

  const localSdp = pc.localDescription?.sdp;
  if (!localSdp) {
    pc.close();
    throw new Error("WHEP: empty local SDP");
  }

  const res = await fetch(whepUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/sdp",
    },
    body: localSdp,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    pc.close();
    throw new Error(`WHEP POST failed (${res.status}): ${text || res.statusText}`);
  }

  const answerSdp = await res.text();
  const resourceUrl =
    res.headers.get("Location") ||
    res.headers.get("location") ||
    null;

  await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

  const close = async () => {
    try {
      if (resourceUrl) {
        // Prefer proxied delete when Location is absolute to MediaMTX
        const delUrl = resourceUrl.startsWith("http")
          ? `/api/mediamtx/whep?resource=${encodeURIComponent(resourceUrl)}`
          : resourceUrl;
        await fetch(delUrl, { method: "DELETE" }).catch(() => undefined);
      }
    } finally {
      pc.close();
      video.srcObject = null;
    }
  };

  return { pc, resourceUrl, close };
}
