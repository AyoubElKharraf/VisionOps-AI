import { AlertGallery } from "@/components/AlertGallery";

export default function AlertsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold">Alert Gallery</h1>
        <p className="mt-1 text-sm text-muted">
          Incidents from PostgreSQL with MinIO snapshot / clip links.
        </p>
      </div>
      <AlertGallery />
    </div>
  );
}
