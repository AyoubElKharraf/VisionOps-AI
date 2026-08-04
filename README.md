# VisionOps AI

<p align="center">
  <strong>Real-time computer vision operations platform for live monitoring, spatial rules, and incident response.</strong>
</p>

<p align="center">
  <a href="https://github.com/AyoubElKharraf/VisionOps-AI/actions/workflows/ci.yml">
    <img alt="VisionOps CI" src="https://github.com/AyoubElKharraf/VisionOps-AI/actions/workflows/ci.yml/badge.svg">
  </a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/UI-Next.js%2015-000000?logo=nextdotjs&logoColor=white">
  <img alt="ONNX Runtime" src="https://img.shields.io/badge/Inference-ONNX%20Runtime-005CED?logo=onnx&logoColor=white">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Runtime-Docker%20Compose-2496ED?logo=docker&logoColor=white">
  <img alt="Playwright" src="https://img.shields.io/badge/E2E-Playwright-2EAD33?logo=playwright&logoColor=white">
</p>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="VisionOps AI Control Center overview" width="100%">
</p>

VisionOps AI turns live camera streams into operational events. It combines low-latency WebRTC playback, YOLO/ONNX inference, ByteTrack identity tracking, multi-camera scaling, polygon ROI rules, tripwire counting, JWT/RBAC access, asynchronous media processing, notifications, retention policies, and Prometheus/Grafana observability in one Docker-based monorepo.

## Highlights

- **Low-latency live monitoring** through MediaMTX WebRTC/WHEP, with HLS and MP4 fallbacks.
- **Real-time detection overlay** synchronized with the rendered video, configurable latency compensation, and an optional **presence heatmap**.
- **Stable object identities** using ByteTrack with Kalman-filtered boxes and short-occlusion recovery.
- **Multi-camera management** with camera CRUD in the UI and **one inference worker per active camera**.
- **RTSP resilience** with exponential backoff reconnect when live streams drop.
- **Spatial analytics** with normalized polygon ROI zones, directional tripwires, and **live occupancy** (`count / capacity` + %).
- **Capacity alerts** when person tracks exceed a zone’s max, separate from classic intrusion (`forbidden_classes`).
- **Loitering / dwell-time** alerts when a tracked person stays in a zone beyond a configured threshold.
- **PPE / hard-hat enforcement** on must-wear ROI zones (optional secondary Ultralytics model via `VISIONOPS_PPE_MODEL`).
- **Scheduled ROI rules** with optional UTC windows and weekday filters (overnight ranges supported).
- **Incident lifecycle**: open, acknowledge, assign, comment, resolve, reopen, and immutable event history.
- **Alert evidence** with snapshots and clips processed asynchronously and stored in MinIO, plus one-click **ZIP incident export** (media + timeline).
- **Dual authentication**: service `X-API-Key` for the engine, JWT sessions + roles (`admin` / `operator`) for humans.
- **Admin user management** UI at `/users` (create operators and admins).
- **Mobile-friendly alert triage** on `/alerts` with sticky Ack/Resolve actions and filter chips.
- **Notifications** via webhook, Slack, and/or SMTP email on lifecycle events.
- **Retention & quotas** for MinIO media and resolved incidents (Celery Beat).
- **Observability** with Prometheus metrics and a provisioned Grafana dashboard.
- **Versioned database schema** with Alembic migrations.
- **Automated quality gates** covering unit, API, tracking, build, and Playwright E2E tests.

## Product tour

### Live Monitor

WebRTC video and WebSocket detections share the same MediaMTX source. Bounding boxes are projected onto `object-contain` video geometry, while per-track velocity compensates for transport and inference delay. Toggle **Heatmap** to visualize temporal person presence (decaying splat grid from foot points).

<p align="center">
  <img src="docs/screenshots/live-monitor.png" alt="Live Monitor with synchronized detections" width="100%">
</p>

### Camera management

Register RTSP/HLS sources, edit metadata, disable cameras, and derive the MediaMTX path from each source URL. In Docker, prefer container-reachable hosts such as `rtsp://mediamtx:8554/cam1`.

<p align="center">
  <img src="docs/screenshots/cameras.png" alt="Camera management" width="100%">
</p>

### ROI Polygon Editor

Draw resolution-independent intrusion, occupancy, or loitering zones. Occupancy mode sets a capacity (max people); loitering mode sets a dwell threshold in seconds. Optionally limit enforcement to a UTC schedule (days + start/end, including overnight). The Live Monitor shows `count / capacity`, `dwell Xs/Ys`, or `off-schedule`, and raises incidents when limits are exceeded. Coordinates are normalized before persistence and synchronized back to the inference engine.

<p align="center">
  <img src="docs/screenshots/roi-editor.png" alt="ROI polygon editor" width="100%">
</p>

### Alert Gallery

Review evidence, filter by status with chips, acknowledge / resolve with large tap targets (sticky on mobile), assign operators, comment, export a ZIP pack, and inspect history.

<p align="center">
  <img src="docs/screenshots/alert-gallery.png" alt="Alert Gallery with MinIO snapshots" width="100%">
</p>

## Architecture

```mermaid
flowchart LR
    Source[Camera / demo MP4] --> Publisher[FFmpeg publisher]
    Publisher --> MediaMTX[MediaMTX<br/>RTSP · WebRTC · HLS]
    MediaMTX --> Browser[Next.js Control Center]
    MediaMTX --> Engine[Multi-cam supervisor<br/>YOLOv8 · ONNX · ByteTrack]

    Engine -->|detections / alerts| API[FastAPI + JWT/RBAC]
    API --> Postgres[(PostgreSQL)]
    API --> Redis[(Redis)]
    Redis --> Worker[Celery worker]
    Redis --> Beat[Celery beat<br/>retention]
    Worker --> MinIO[(MinIO<br/>snapshots · clips)]
    API -->|WebSocket detections| Browser
    API -->|cameras · ROI · incidents · users| Browser
    MinIO -->|presigned media URLs| Browser
    API --> Prom[Prometheus]
    Engine --> Prom
    Prom --> Grafana[Grafana]
```

### Components

| Component | Technology | Responsibility |
| --- | --- | --- |
| `visionops-engine` | Python, YOLOv8, ONNX Runtime, OpenCV, ByteTrack, Shapely | Multi-cam supervisor, detection, tracking, ROI/tripwire, RTSP reconnect |
| `visionops-backend` | FastAPI, SQLAlchemy, Alembic, Celery, PyJWT | REST/WS API, auth, persistence, notifications, retention jobs |
| `visionops-ui` | Next.js 15, React 19, Tailwind CSS | Login, dashboard, overlays, admin users |
| Streaming | MediaMTX, FFmpeg | RTSP ingest/publish, WebRTC/WHEP and HLS delivery |
| Data | PostgreSQL, Redis, MinIO | Relational data, task queue and object storage |
| Observability | Prometheus, Grafana | Metrics scrape and provisioned overview dashboard |
| Quality | Pytest, Ruff, Node Test Runner, Playwright | Unit, API, tracking and end-to-end validation |

## Quick start

### Prerequisites

- Docker Desktop with Docker Compose v2
- Git
- At least 8 GB RAM recommended for the first image build

Python 3.11+ and Node.js 20+ are only required for development outside Docker.

### Start the complete stack

```powershell
git clone <repository-url>
cd VisionOps_AI
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

The first engine build/install can take several minutes. The engine image explicitly uses **CPU-only PyTorch wheels** to avoid downloading CUDA runtime packages; production inference runs through ONNX Runtime.

### First login

1. Open [http://localhost:3000/login](http://localhost:3000/login)
2. Sign in with the bootstrap admin (defaults):
   - Username: `admin`
   - Password: `visionops-admin`
3. Create operators from **Users** (admin only), manage cameras under **Cameras**, then open **Live Monitor**.

Change `VISIONOPS_JWT_SECRET` and the admin password before any shared or production deployment.

### Open the services

| Service | URL |
| --- | --- |
| Control Center | [http://localhost:3000](http://localhost:3000) |
| Login | [http://localhost:3000/login](http://localhost:3000/login) |
| API health | [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health) |
| OpenAPI documentation | [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) |
| Prometheus | [http://127.0.0.1:9090](http://127.0.0.1:9090) |
| Grafana | [http://127.0.0.1:3001](http://127.0.0.1:3001) (`admin` / `admin`) |
| HLS demo stream | [http://127.0.0.1:8888/cam1/index.m3u8](http://127.0.0.1:8888/cam1/index.m3u8) |
| MinIO console | [http://127.0.0.1:9002](http://127.0.0.1:9002) |

The Compose stack contains **12 services**:

```text
mediamtx · publisher · postgres · redis · minio
backend · worker · beat · engine · ui
prometheus · grafana
```

### Useful operations

```powershell
# Follow application logs
docker compose logs -f backend worker beat engine ui publisher

# Rebuild application services after code changes
docker compose up -d --build backend worker beat engine ui prometheus grafana

# Validate the demo stream
curl http://127.0.0.1:8888/cam1/index.m3u8

# Stop the stack
docker compose down
```

To reset all local database/object-storage volumes:

```powershell
# Destructive: removes local VisionOps data
docker compose down -v
```

## Runtime flow

1. The `publisher` service loops `visionops-engine/data/demo.mp4` into MediaMTX path `cam1`.
2. The browser receives that stream using WebRTC/WHEP (after JWT login).
3. The engine **multi-cam supervisor** polls active cameras and runs one `demo_roi` worker per camera (fallback: `VIDEO_SOURCE` + `CAMERA_NAME`).
4. Each worker performs ONNX inference, ByteTrack IDs, ROI/tripwire rules, and reconnects on RTSP failures.
5. Detections stream to the UI over WebSocket; alerts are posted to FastAPI.
6. Celery generates snapshot/clip evidence in MinIO; Beat applies retention policies.
7. Operators handle incidents in the Alert Gallery; optional webhook/Slack/email notifications fire on configured events.

## Tracking and overlay synchronization

ByteTrack is enabled by default:

```powershell
cd visionops-engine
python demo_roi.py --tracker bytetrack `
  --track-low-thresh 0.10 `
  --track-high-thresh 0.25 `
  --track-buffer 30
```

The previous nearest-centroid tracker remains available for diagnostics:

```powershell
python demo_roi.py --tracker centroid
```

The frontend uses each `track_id` to estimate object velocity and compensate for residual video/detection latency. The Live Monitor exposes a latency slider for environment-specific fine tuning.

## Configuration

Copy `.env.example` to `.env`, then review at least:

```dotenv
VISIONOPS_API_KEY=visionops-dev-key
VISIONOPS_JWT_SECRET=visionops-dev-jwt-secret-change-me
VISIONOPS_ADMIN_USERNAME=admin
VISIONOPS_ADMIN_PASSWORD=visionops-admin
ENGINE_MODE=multi
CAMERA_NAME=demo-camera
VIDEO_SOURCE=rtsp://mediamtx:8554/cam1
YOLO_CONF=0.25
USE_ONNX=true
MINIO_PUBLIC_ENDPOINT=127.0.0.1:9001
```

The included values are for **local development only**. Use strong, externally managed secrets and HTTPS in production.

### Authentication

VisionOps supports dual authentication:

| Actor | Mechanism | Notes |
| --- | --- | --- |
| Engine / workers | `X-API-Key` or `?api_key=` | Service principal with admin-equivalent access |
| Humans (UI) | `Authorization: Bearer <JWT>` | Login at `/login`; roles `admin` / `operator` |
| Detection WebSocket | `?token=<JWT>` or `?api_key=` | Browsers cannot set custom headers |

- `/health`, `GET /metrics`, and `GET /api/v1/auth/status` remain public (or scrape-friendly).
- **admin**: camera CRUD, user creation (UI `/users`), alert delete, retention trigger, full incident workflow.
- **operator**: read cameras/monitor/ROI, run incident workflow; no camera CRUD or user management.
- On first boot with `VISIONOPS_JWT_SECRET` set and an empty `users` table, the backend creates the bootstrap admin (`admin` / `visionops-admin` by default).

### Observability

Prometheus scrapes:

| Target | URL |
| --- | --- |
| Backend | `http://127.0.0.1:8001/metrics` |
| Engine supervisor | `http://127.0.0.1:9101/metrics` |
| Prometheus UI | [http://127.0.0.1:9090](http://127.0.0.1:9090) |
| Grafana | [http://127.0.0.1:3001](http://127.0.0.1:3001) (default `admin` / `admin`) |

Key series include: `visionops_engine_fps`, `visionops_engine_infer_ms`, `visionops_engine_stream_up`, `visionops_engine_reconnects_total`, `visionops_engine_workers`, `visionops_http_request_duration_seconds`, `visionops_alerts_created_total`, `visionops_celery_queue_depth`.

The **VisionOps Overview** dashboard is provisioned automatically under the VisionOps folder in Grafana.

### RTSP resilience

The engine wraps live sources (`rtsp://`, `http://`, …) in `RobustCapture`:

- Retries the initial open with exponential backoff
- Reconnects after consecutive failed reads (does not exit the process)
- File sources still stop at EOF (no reconnect loop)

Tunables: `RTSP_RECONNECT`, `RTSP_RECONNECT_INITIAL`, `RTSP_RECONNECT_MAX`, `RTSP_FAIL_THRESHOLD`, `RTSP_OPEN_RETRIES`.

### Multi-camera scale

By default (`ENGINE_MODE=multi`) the engine container runs `multi_cam_runner.py`:

1. Polls `GET /api/v1/cameras?active_only=true` every `CAMERA_POLL_SECONDS`
2. Starts one `demo_roi.py` subprocess per active camera (`source_url` + `name`)
3. Restarts workers when a source URL changes or a process crashes
4. Falls back to `VIDEO_SOURCE` + `CAMERA_NAME` when the API has no cameras yet

Set `ENGINE_MODE=single` for the legacy single-stream process. Add cameras in the UI (`/cameras`) to scale inference without rebuilding images.

When the engine runs in Docker, set each camera `source_url` to a container-reachable host (e.g. `rtsp://mediamtx:8554/cam1`), not `127.0.0.1`.

### Notifications

Configure one or more channels in `.env` (empty = disabled). Delivery runs asynchronously on the Celery worker.

| Channel | Variables |
| --- | --- |
| Generic webhook | `NOTIFY_WEBHOOK_URL` — JSON POST with `event_type`, alert fields, `dashboard_url` |
| Slack | `NOTIFY_SLACK_WEBHOOK_URL` — Incoming Webhook |
| Email | `NOTIFY_EMAIL_TO` + `NOTIFY_SMTP_HOST` (+ optional user/password/TLS) |

`NOTIFY_EVENTS` defaults to `created,resolved` (use `all` for every lifecycle event).  
Status: `GET /api/v1/notifications/status` (authenticated).

### Retention and storage quotas

Automatic Celery Beat job (service `beat`) applies three policies:

1. **Media age** — delete MinIO snapshots/clips for alerts older than `RETENTION_MEDIA_DAYS` (default 30).
2. **Resolved incidents** — delete resolved alert rows (+ media) older than `RETENTION_RESOLVED_ALERT_DAYS` (default 90).
3. **Bucket quota** — if `alerts/` usage exceeds `RETENTION_BUCKET_QUOTA_MB` (default 5120), delete oldest objects until under quota.

| Endpoint | Access |
| --- | --- |
| `GET /api/v1/retention/status` | Authenticated |
| `POST /api/v1/retention/run?dry_run=true&async_run=false` | Admin |

### Database migrations

The backend automatically runs `alembic upgrade head` during startup.

```powershell
cd visionops-backend
.\.venv\Scripts\Activate.ps1

alembic current
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
```

## API overview

| Area | Main endpoints |
| --- | --- |
| Auth | `POST /api/v1/auth/login`, `GET /me`, `GET/POST /users`, `GET /status` |
| Metrics | `GET /metrics` (Prometheus text), engine `:9101/metrics` |
| Notifications | `GET /api/v1/notifications/status` |
| Retention | `GET /api/v1/retention/status`, `POST /api/v1/retention/run` |
| Cameras | `GET/POST /api/v1/cameras`, `PATCH/DELETE /api/v1/cameras/{id}` |
| ROI zones | `GET/POST /api/v1/roi-zones`, `DELETE /api/v1/roi-zones/{id}` |
| Detections | `POST /api/v1/detections`, `GET /api/v1/detections/latest` |
| Live detections | `WS /api/v1/ws/detections` |
| Alerts | `GET/POST /api/v1/alerts`, `GET/DELETE /api/v1/alerts/{id}`, `GET /api/v1/alerts/{id}/export` (ZIP evidence pack) |
| Incident workflow | `acknowledge`, `assign`, `comments`, `resolve`, `reopen`, `events` |

See the interactive OpenAPI documentation at [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs).

## Development

### Engine

```powershell
cd visionops-engine
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Single camera
python demo_roi.py --skip-benchmark --max-frames 0 `
  --source rtsp://127.0.0.1:8554/cam1 `
  --stream-detections --post-alerts --sync-roi `
  --api-url http://127.0.0.1:8001 `
  --api-key visionops-dev-key

# Multi-camera supervisor (polls active cameras from the API)
python multi_cam_runner.py `
  --api-url http://127.0.0.1:8001 `
  --api-key visionops-dev-key `
  --fallback-source rtsp://127.0.0.1:8554/cam1 `
  --fallback-camera demo-camera
```

### Backend and worker

```powershell
cd visionops-backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Second terminal — media + notification tasks
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo

# Third terminal — retention schedule
celery -A app.celery_app.celery_app beat --loglevel=info
```

### UI

```powershell
cd visionops-ui
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

## Testing & CI

Every push and pull request to `main` runs **VisionOps CI** on GitHub Actions:

| Job | Gate |
| --- | --- |
| Engine | Ruff + unit tests (tracker, ROI, ONNX, reconnect, multi-cam) |
| Backend | Ruff + API tests against Postgres (auth, incidents, metrics, retention) |
| UI | Unit tests, TypeScript, production build |
| E2E | Playwright Chromium against a disposable `docker compose` stack (login JWT + cameras/ROI/incidents) |

Latest status: [![VisionOps CI](https://github.com/AyoubElKharraf/VisionOps-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/AyoubElKharraf/VisionOps-AI/actions/workflows/ci.yml)

Current local baseline:

- **Engine:** 34 tests — ByteTrack, ROI analytics, heatmap, PPE, ONNX, RTSP reconnect, multi-cam supervisor
- **Backend:** 40 tests — JWT/API-key auth, metrics, notifications, retention, incidents, ZIP export
- **UI:** 15 unit tests — WHEP security, geometry, stream paths, overlay sync
- **E2E:** 3 Playwright scenarios — camera CRUD, ROI CRUD, incident workflow (admin JWT injected)

Failed E2E runs keep screenshots, video, traces, and an HTML report as CI artifacts.

### Run locally

```powershell
# Engine
cd visionops-engine
.\.venv\Scripts\python.exe -m pytest tests -q

# Backend
cd ..\visionops-backend
.\.venv\Scripts\python.exe -m pytest tests -q

# UI unit/type checks
cd ..\visionops-ui
npm run test:unit
npx tsc --noEmit

# Playwright against the running Docker stack
npm run test:e2e:install
npm run test:e2e
```

## Repository layout

```text
VisionOps_AI/
├── .github/workflows/ci.yml
├── deploy/
│   ├── grafana/                 # datasource + VisionOps Overview dashboard
│   └── prometheus/              # scrape config (backend + engine)
├── docker/
├── docs/screenshots/
├── scripts/
├── visionops-backend/
│   ├── alembic/
│   ├── app/                     # auth, metrics, notifications, retention, routers
│   └── tests/
├── visionops-engine/
│   ├── multi_cam_runner.py      # one worker process per active camera
│   ├── stream_capture.py        # RTSP reconnect / backoff
│   ├── metrics_server.py
│   ├── demo_roi.py
│   ├── byte_tracker.py
│   ├── run_engine.sh            # ENGINE_MODE=multi|single entrypoint
│   └── tests/
├── visionops-ui/
│   ├── app/                     # login, users, cameras, monitor, roi, alerts
│   ├── components/
│   ├── e2e/
│   └── lib/
├── docker-compose.yml           # 12 services including beat, prometheus, grafana
└── .env.example
```

## Project status

- [x] ONNX detection pipeline
- [x] MediaMTX WebRTC/HLS streaming
- [x] Multi-camera CRUD and selection
- [x] ROI and tripwire rules
- [x] ByteTrack identity tracking
- [x] Video/overlay latency compensation
- [x] Alert evidence in MinIO
- [x] Incident lifecycle and history
- [x] Alembic migrations
- [x] API-key authentication and WHEP target hardening
- [x] Unit/API/E2E CI pipeline
- [x] User accounts, JWT, and role-based access control
- [x] Admin users UI (`/users`)
- [x] Prometheus/Grafana observability
- [x] Notification integrations (email/webhook/Slack)
- [x] Retention policies and storage quotas
- [x] RTSP reconnect / stream resilience
- [x] Multi-camera engine scaling (one worker per camera)
- [x] Zone occupancy counting (`count/capacity`, over-capacity alerts)
- [x] Loitering / dwell-time zone alerts
- [x] Scheduled ROI rule windows (UTC hours + weekdays)
- [x] Live presence heatmap overlay on the monitor
- [x] PPE / hard-hat must-wear zone alerts
- [x] Incident ZIP evidence export (snapshot/clip/timeline)
- [x] Mobile-friendly alert triage (sticky Ack/Resolve)

## License

See the repository license file if present; otherwise treat as a private/academic project unless otherwise stated.
