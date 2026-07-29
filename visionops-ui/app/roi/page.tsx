"use client";

import Link from "next/link";
import { RoiEditor } from "@/components/RoiEditor";
import { CameraSelect } from "@/components/CameraSelect";
import { useSelectedCamera } from "@/lib/useSelectedCamera";

export default function RoiPage() {
  const { cameras, selected, selectedId, selectCamera, loading, error } =
    useSelectedCamera();

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold">ROI Polygon Editor</h1>
          <p className="mt-1 text-sm text-muted">
            Define intrusion zones for the selected camera. Points are stored
            normalized and applied on the live monitor.
          </p>
        </div>
        <CameraSelect
          cameras={cameras}
          selectedId={selectedId}
          onChange={selectCamera}
          loading={loading}
        />
      </div>

      {error && (
        <p className="rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </p>
      )}

      {!loading && !selected && (
        <p className="rounded-md border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          No camera selected.{" "}
          <Link href="/cameras" className="text-accent underline">
            Create a camera
          </Link>{" "}
          first.
        </p>
      )}

      {selected && <RoiEditor cameraName={selected.name} />}
    </div>
  );
}
