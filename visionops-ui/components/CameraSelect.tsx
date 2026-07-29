"use client";

import type { Camera } from "@/lib/api";

type Props = {
  cameras: Camera[];
  selectedId: string | null;
  onChange: (id: string) => void;
  loading?: boolean;
  allowAll?: boolean;
  className?: string;
};

export function CameraSelect({
  cameras,
  selectedId,
  onChange,
  loading = false,
  allowAll = false,
  className,
}: Props) {
  return (
    <label className={className ?? "flex flex-col gap-1 text-sm text-muted"}>
      <span>Camera</span>
      <select
        value={selectedId ?? (allowAll ? "" : "")}
        disabled={loading || (!allowAll && cameras.length === 0)}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-11 min-w-[14rem] rounded-md border border-white/15 bg-ink px-3 text-white outline-none focus:border-accent disabled:opacity-50"
      >
        {allowAll && <option value="">All cameras</option>}
        {!allowAll && cameras.length === 0 && (
          <option value="">No cameras — create one</option>
        )}
        {cameras.map((cam) => (
          <option key={cam.id} value={cam.id}>
            {cam.name}
            {cam.location ? ` · ${cam.location}` : ""}
            {!cam.is_active ? " (inactive)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
