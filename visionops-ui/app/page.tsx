import { Camera, Activity } from "lucide-react";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
      <div className="mb-8 flex items-center gap-3 text-accent">
        <Camera className="h-8 w-8" strokeWidth={1.75} />
        <span className="font-display text-sm font-semibold tracking-[0.2em] uppercase">
          VisionOps AI
        </span>
      </div>

      <h1 className="font-display text-4xl font-semibold tracking-tight sm:text-5xl">
        Control Center
      </h1>
      <p className="mt-4 max-w-xl text-lg text-muted">
        Real-time computer vision platform for RTSP / WebRTC monitoring,
        YOLO detection, and anomaly alerts.
      </p>

      <div className="mt-10 flex items-center gap-3 rounded-lg border border-white/10 bg-panel/80 px-4 py-3">
        <Activity className="h-5 w-5 text-accent" />
        <div>
          <p className="text-sm font-medium">Phase 1 — infra ready</p>
          <p className="text-xs text-muted">
            Docker stack + YOLO engine online. WebRTC monitor arrives in Phase 4.
          </p>
        </div>
      </div>
    </main>
  );
}
