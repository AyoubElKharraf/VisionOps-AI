import { RoiEditor } from "@/components/RoiEditor";

export default function RoiPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold">ROI Polygon Editor</h1>
        <p className="mt-1 text-sm text-muted">
          Define intrusion zones. Points are stored normalized and applied on the live monitor.
        </p>
      </div>
      <RoiEditor />
    </div>
  );
}
