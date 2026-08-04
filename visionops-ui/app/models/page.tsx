import { ModelRegistry } from "@/components/ModelRegistry";

export default function ModelsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold">Model registry</h1>
        <p className="mt-1 text-sm text-muted">
          Upload, version, and activate detector / PPE weights. Admin only.
        </p>
      </div>
      <ModelRegistry />
    </div>
  );
}
