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

## Backend skeleton

```powershell
cd visionops-backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

## UI skeleton

```powershell
cd visionops-ui
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

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

:: Export ONNX (skipped if yolov8n.onnx already exists)
python export_onnx.py

:: Inference ONNX
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

## Repository layout

```text
VisionOps_AI/
├── docker/
├── scripts/test-phase1.ps1
├── scripts/test-phase2.ps1
├── visionops-engine/       # YOLO / OpenCV / ONNX / ROI (Phases 1–2)
├── visionops-backend/
├── visionops-ui/
├── docker-compose.yml
└── .env.example
```

## Roadmap

- **Phase 2** — ONNX export + ROI geometry (Shapely) ✅
- **Phase 3** — Alerts API + Celery clip upload to MinIO
- **Phase 4** — WebRTC player + Canvas overlay + ROI editor
- **Phase 5** — CI/CD + performance tests
