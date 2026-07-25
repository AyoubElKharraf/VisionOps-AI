import { NextRequest, NextResponse } from "next/server";

/**
 * Same-origin proxy for MediaMTX WHEP signaling (avoids browser CORS).
 *
 * POST   /api/mediamtx/whep?path=cam1     → POST http://host:8889/cam1/whep
 * DELETE /api/mediamtx/whep?resource=URL  → DELETE session resource
 */

const MEDIAMTX_WEBRTC =
  process.env.MEDIAMTX_WEBRTC_BASE ?? "http://127.0.0.1:8889";

export async function POST(req: NextRequest) {
  const path = req.nextUrl.searchParams.get("path") || "cam1";
  const target = `${MEDIAMTX_WEBRTC.replace(/\/$/, "")}/${path}/whep`;
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/sdp",
      },
      body,
      cache: "no-store",
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: "MediaMTX unreachable",
        target,
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }

  const answer = await upstream.text();
  const headers = new Headers();
  headers.set("Content-Type", upstream.headers.get("Content-Type") || "application/sdp");

  const location = upstream.headers.get("Location") || upstream.headers.get("location");
  if (location) {
    // Expose absolute MediaMTX resource URL to the client for DELETE
    headers.set("Location", location);
    headers.set("Access-Control-Expose-Headers", "Location");
  }

  return new NextResponse(answer, {
    status: upstream.status,
    headers,
  });
}

export async function DELETE(req: NextRequest) {
  const resource = req.nextUrl.searchParams.get("resource");
  if (!resource) {
    return NextResponse.json({ error: "missing resource" }, { status: 400 });
  }

  try {
    const upstream = await fetch(resource, {
      method: "DELETE",
      cache: "no-store",
    });
    return new NextResponse(null, { status: upstream.status });
  } catch (err) {
    return NextResponse.json(
      {
        error: "DELETE failed",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Methods": "POST, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
