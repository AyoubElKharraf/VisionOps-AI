# VisionOps AI

Real-time computer vision & video surveillance platform — monorepo for **Computer Vision**, **low-latency streaming**, and **Edge/Cloud processing**.

## Architecture (Phase 1)

| Module | Stack | Role |
|--------|--------|------|
| `visionops-engine` | Python 3.11, YOLOv8, OpenCV | Frame-by-frame detection |
| `visionops-backend` | FastAPI, Celery, SQLAlchemy | API skeleton (`GET /health`) |
| `visionops-ui` | Next.js 15, Tailwind, Lucide | Dashboard shell |
| Infra | MediaMTX, Postgres 16, Redis 7, MinIO | Streaming + storage + queue |

## Prerequisites

- Docker Desktop / Docker Compose v2
- Python **3.11+** (3.12 recommended on Windows)
- Node.js **20+** (UI only)
- PowerShell 5+ (Windows test script)

## Quick start — infrastructure

```powershell
cd VisionOps_AI
Copy-Item .env.example .env
docker compose up -d
docker compose ps
```

| Service | Host ports |
|---------|------------|
| MediaMTX RTSP / WebRTC / RTMP | `8554` / `8889` / `1935` |
| PostgreSQL | `5434` *(évite conflits NeuroFlow / autres Postgres locaux)* |
| Redis | `6380` |
| MinIO API / Console | `9001` / `9002` |

Default MinIO login (see `.env.example`): `visionops_minio` / `visionops_minio_secret`.

## Quick start — inference engine

Le venv est déjà créé sous `visionops-engine/.venv` (Python 3.12).  
**Important :** dans **CMD**, utilise `activate.bat` (pas `Activate.ps1`), ou appelle directement le Python du venv.

### CMD (Invite de commandes)

```bat
cd visionops-engine
.\.venv\Scripts\activate.bat
python main.py --max-frames 60 --output data\annotated_output.mp4 --device cpu
```

Sans activer le venv :

```bat
cd visionops-engine
.\.venv\Scripts\python.exe main.py --max-frames 60 --device cpu
```

### PowerShell

```powershell
cd visionops-engine
.\.venv\Scripts\Activate.ps1
python main.py --max-frames 60 --output data/annotated_output.mp4 --device cpu

# RTSP / fichier local
python main.py --source rtsp://localhost:8554/cam1
python main.py --source path\to\video.mp4 --show
```

Smoke test (PowerShell uniquement — ne pas coller de commentaire `# ...` sur la même ligne) :

```powershell
.\scripts\test-phase1.ps1 -SkipDocker -MaxFrames 15
```

Docker image for the engine:

```powershell
docker build -t visionops-engine ./visionops-engine
docker run --rm -v ${PWD}/visionops-engine/data:/app/data visionops-engine python main.py --max-frames 30 --output data/out.mp4
```

## Backend (Phase 3)

```powershell
cd visionops-backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# API (use 8001 if :8000 is busy on Windows)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Celery worker (solo pool required on Windows) — second terminal
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
```

- Health: [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health)
- Docs: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)
- `POST /api/v1/cameras` · `POST /api/v1/alerts` · `GET /api/v1/alerts`

## UI — Phase 4 Control Center

```powershell
cd visionops-ui
copy .env.local.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Pages:
- `/` Overview (API health)
- `/monitor` **WebRTC (MediaMTX WHEP)** / HLS / demo + canvas boxes
- `/roi` Polygon ROI editor (persisted via API)
- `/alerts` Alert gallery (MinIO snapshots/clips)

### Real WebRTC via MediaMTX

1. Start infra: `docker compose up -d` (exposes `8889` WHEP + `8189/udp` ICE)
2. Publish demo loop (needs [ffmpeg](https://ffmpeg.org) in PATH):

```powershell
.\scripts\publish-demo-mediamtx.ps1
```

3. Open [http://localhost:3000/monitor](http://localhost:3000/monitor) → source **WebRTC · MediaMTX WHEP**
4. (Optional) stream detections for canvas overlay:

```bat
cd visionops-engine
.\.venv\Scripts\activate.bat
python demo_roi.py --skip-benchmark --max-frames 0 --stream-detections --stream-every 2 --api-url http://127.0.0.1:8001
```

WHEP signaling is proxied by Next.js (`/api/mediamtx/whep`) to avoid browser CORS.

## Phase 1 smoke test

```powershell
.\scripts\test-phase1.ps1
.\scripts\test-phase1.ps1 -SkipEngine
.\scripts\test-phase1.ps1 -SkipDocker -MaxFrames 15
```

## Phase 2 — ONNX + ROI / Tripwire

```bat
cd visionops-engine
.\.venv\Scripts\activate.bat
pip install -r requirements.txt

:: Export ONNX imgsz=416 (CPU-fast, default)
python export_onnx.py
:: Optional higher-accuracy 640:
python export_onnx.py --imgsz 640 --output yolov8n_640.onnx --force

:: Inference ONNX (uses yolov8n_416.onnx by default)
python main.py --use-onnx --max-frames 60 --device cpu

:: ROI demo (zone + tripwire + PyTorch vs ONNX metrics)
python demo_roi.py --max-frames 90 --benchmark-frames 30 --device cpu
```

PowerShell smoke test:

```powershell
.\scripts\test-phase2.ps1
.\scripts\test-phase2.ps1 -MaxFrames 60 -BenchmarkFrames 20
```

New engine modules: `export_onnx.py`, `onnx_engine.py`, `roi_manager.py`, `demo_roi.py`.

## Phase 3 — Alerts API + Celery + MinIO

Pipeline: engine ROI/tripwire → `POST /api/v1/alerts` → PostgreSQL → Celery worker → snapshot JPG + clip MP4 on MinIO.

```bat
:: Terminal 1 — infra
docker compose up -d

:: Terminal 2 — API
cd visionops-backend
.\.venv\Scripts\activate.bat
uvicorn app.main:app --host 127.0.0.1 --port 8001

:: Terminal 3 — Celery
cd visionops-backend
.\.venv\Scripts\activate.bat
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo

:: Terminal 4 — engine posts alerts
cd visionops-engine
.\.venv\Scripts\activate.bat
python demo_roi.py --skip-benchmark --max-frames 60 --post-alerts --api-url http://127.0.0.1:8001
```

PowerShell smoke test:

```powershell
.\scripts\test-phase3.ps1
```

## Repository layout

```text
VisionOps_AI/
├── docker/
├── .github/workflows/ci.yml
├── scripts/test-phase1.ps1 … test-phase5.ps1
├── scripts/bench_phase5.py
├── visionops-engine/       # YOLO / ONNX / ROI + tests
├── visionops-backend/      # FastAPI + Celery + MinIO + tests
├── visionops-ui/
├── docker-compose.yml
└── .env.example
```

## Phase 5 — CI/CD & performance tests

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR:
- **Engine**: Ruff + pytest (ROI geometry, NMS / letterbox)
- **Backend**: Ruff + API tests against Postgres service
- **UI**: `tsc --noEmit` + `next build`

Local validation:

```powershell
docker compose up -d
.\scripts\test-phase5.ps1
# tests only:
.\scripts\test-phase5.ps1 -SkipBench
```

ONNX bench only:

```bat
cd visionops-engine
.\.venv\Scripts\activate.bat
python ..\scripts\bench_phase5.py --frames 60
```

## Roadmap

- **Phase 2** — ONNX export + ROI geometry (Shapely) ✅
- **Phase 3** — Alerts API + Celery clip upload to MinIO ✅
- **Phase 4** — Dashboard + canvas overlay + ROI editor + alert gallery ✅
- **Phase 5** — CI/CD + performance tests ✅
