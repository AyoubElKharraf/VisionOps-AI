"""VisionOps AI — Core API (Phase 1 skeleton)."""

from fastapi import FastAPI

app = FastAPI(
    title="VisionOps AI Backend",
    description="Real-time computer vision platform API",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "visionops-backend"}
