import { CameraManager } from "@/components/CameraManager";

export default function CamerasPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold">Cameras</h1>
        <p className="mt-1 text-sm text-muted">
          Add, edit, or remove cameras. The last path segment of an RTSP/HLS URL
          becomes the MediaMTX stream name (e.g. <code>cam1</code>).
        </p>
      </div>
      <CameraManager />
    </div>
  );
}
