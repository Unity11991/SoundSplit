---
title: SoundSplit AI API
emoji: 🎵
colorFrom: purple
colorTo: indigo
sdk: gradio
sdk_version: 4.44.1
app_file: app.py
pinned: false
license: mit
---

# StemLab AI — Production AI Vocal & Music Separator

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/next.js-16.4-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Demucs v4](https://img.shields.io/badge/Model-Demucs%20v4%20(htdemucs)-8B5CF6.svg)](https://github.com/facebookresearch/demucs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSES.md)

**StemLab AI** is a production-grade, asynchronous AI audio source-separation platform. It separates uploaded music and audio into isolated stems (**Vocals & Instrumental** in 2-stem mode; **Vocals, Drums, Bass, and Other** in 4-stem mode) using real deep transformer models (Meta's **Demucs v4 / `htdemucs`**).

The application features a dark, professional online audio workstation interface with a synchronized Web Audio API mixer, solo/mute matrix, volume faders, real-time waveform visualization, A/B reference switching, and lossless ZIP exports.

---

## Architecture Overview

```
+-------------------------------------------------------------------------------+
|                                CLIENT BROWSER                                 |
| Next.js 14+ / React / Tailwind CSS / Web Audio API Engine / HTML5 Waveforms   |
+---------------------------------------+---------------------------------------+
                                        | HTTPS / REST & SSE
                                        v
+-------------------------------------------------------------------------------+
|                            REVERSE PROXY / NGINX                              |
|   - Rate Limiting   - Static Caching   - SSL/TLS Termination   - CORS Security|
+---------------------------------------+---------------------------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
+----------------------------------+          +----------------------------------+
|           FASTAPI API            |          |         NEXT.JS WEB APP          |
| - Media probing & validation     |          | - Audio workstation UX           |
| - Signed URLs & access control   |          | - Synchronized multi-track mixer |
| - Job queue dispatch             |          | - A/B comparison engine          |
| - SSE state event stream         |          | - Real-time waveform rendering   |
+----------------+-----------------+          +----------------------------------+
                 |
        +--------+--------+
        |                 |
        v                 v
+---------------+ +---------------+
|  POSTGRESQL   | |  REDIS QUEUE  |
| - Projects    | | - Job Queue   |
| - Stems       | | - Events/PubSub|
| - Sessions    | | - Worker Heart|
+---------------+ +-------+-------+
                          |
                          v
+-------------------------------------------------------------------------------+
|                            AI WORKER (CELERY / ARQ)                           |
| - FFprobe & FFmpeg media normalization & validation                           |
| - Demucs Model Adapter (Torch / CUDA / CPU fallback)                          |
| - Chunking, Overlap blending, Reconstruction                                  |
| - Stem export (WAV / MP3) & ZIP archive generation                            |
| - Object / Local Storage adapter                                              |
+-------------------------------------------------------------------------------+
```

---

## Key Features

1. **Real Deep Neural Audio Separation**:
   - Powered by Meta AI's Demucs v4 Hybrid Transformer (`htdemucs`).
   - 2-Stem Mode: Vocals + Instrumental (exact residual reconstruction).
   - 4-Stem Mode: Vocals, Drums, Bassline, and Synths/Other instruments.
2. **Synchronized Multi-Stem Audio Engine**:
   - Built on the Web Audio API with a shared audio clock.
   - Solo (`S`) and Mute (`M`) buttons per track with DAW-style LED states.
   - Individual track volume faders (0% to 150%) with double-click reset.
   - Master volume and Transport controls (Play/Pause with Spacebar shortcut, Stop).
   - Seamless **A/B Comparison Switch** (crossfade instantly between Original Audio and Separated Mix at the exact same playback position).
   - Interactive canvas waveforms with click-to-seek support.
3. **Resilient Asynchronous Job Architecture**:
   - Web server never blocks during heavy AI inference.
   - Real-time Server-Sent Events (SSE) stream (`/api/v1/separations/{id}/events`).
   - Redis queue for distributed worker clusters with an automatic in-process fallback worker for standalone environments.
4. **Export & Download System**:
   - Direct download of individual stems in lossless 16-bit 44.1kHz WAV.
   - Single-click streaming ZIP archive export containing all isolated stems.
5. **Security & Data Privacy**:
   - Strict media inspection with FFprobe rejecting non-audio and malicious files.
   - Path traversal mitigation and random UUID storage keys.
   - Insecure Direct Object Reference (IDOR) protection using cryptographic session ownership checks.
   - Short-lived HMAC-SHA256 signed download tokens.
   - Automatic 24-hour retention cleanup policy.

---

## Repository Structure

```
stemlab-ai/
├── apps/
│   ├── web/                    # Next.js 14+ TypeScript frontend
│   ├── api/                    # FastAPI backend REST service & SSE
│   └── worker/                 # AI audio inference worker
├── packages/
│   └── shared-types/           # Shared TypeScript/JSON contracts
├── infrastructure/
│   ├── docker/                 # Container images (API, Worker, Web)
│   ├── nginx/                  # Reverse proxy & routing config
│   └── monitoring/             # Prometheus scrape configuration
├── models/
│   └── README.md               # Model architecture & weight specifications
├── scripts/
│   ├── run_all.py              # Single-command dev launcher
│   └── create_test_audio.py    # Synthetic multi-track audio generator
├── tests/
│   ├── unit/                   # Unit test suites (Storage, Validation, Model)
│   └── integration/            # Real AI end-to-end integration tests
├── docker-compose.yml          # Containerized multi-service orchestration
├── .env.example                # Environment variables template
├── SECURITY.md                 # Security & audio retention policy
├── LICENSES.md                 # Open-source third-party licenses
└── README.md                   # System documentation
```

---

## Quickstart: Local Development

### Prerequisites
- **Python**: 3.10+ (tested on Python 3.12)
- **Node.js**: v20+ and `npm`
- **FFmpeg & FFprobe**: Installed and available in system PATH (`ffmpeg -version`, `ffprobe -version`)

### 1. Setup Virtual Environment & Dependencies
```bash
# Create and activate Python virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Linux/macOS:
source .venv/bin/activate

# Install backend dependencies
pip install -r apps/api/requirements.txt

# Install frontend web dependencies
cd apps/web
npm install
cd ../..
```

### 2. Generate Synthetic Test Audio (Optional)
```bash
python scripts/create_test_audio.py
```

### 3. Run All Services
```bash
python scripts/run_all.py
```
Open your browser to:
- **Studio Web Workstation**: [http://localhost:3000](http://localhost:3000)
- **FastAPI OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Readiness Check**: [http://localhost:8000/api/v1/readiness](http://localhost:8000/api/v1/readiness)

---

## Docker & Production Deployment

StemLab AI is fully containerized with Docker Compose.

```bash
# Build and run the entire stack (PostgreSQL, Redis, API, Worker, Web, NGINX)
docker compose up -d --build

# View real-time logs
docker compose logs -f

# Check container status
docker compose ps
```

The application will be accessible directly on Port `80` ([http://localhost](http://localhost)).

### Enabling GPU Acceleration in Docker
To enable NVIDIA GPU acceleration in the AI worker:
1. Ensure the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) is installed on the host.
2. In `docker-compose.yml`, uncomment the `deploy.resources.reservations.devices` block in the `worker` service.

---

## Running Automated Tests

StemLab AI includes real unit and end-to-end integration tests.

```bash
# Run unit tests (Storage, validation, path traversal, audio limits)
pytest -v tests/unit

# Run full end-to-end AI separation pipeline test
pytest -v tests/integration/test_api_pipeline.py
```

### Test Suite Summary
- `tests/unit/test_storage.py`: Verifies path traversal rejection, safe storage resolution, and signed token life-cycle.
- `tests/unit/test_validation.py`: Verifies magic bytes, container inspection with `ffprobe`, duration limits, and corrupt file rejection.
- `tests/unit/test_models.py`: Verifies Demucs adapter initialization, peak normalization to `-0.5 dBFS`, and waveform peak generation.
- `tests/integration/test_api_pipeline.py`: Executes the full workflow: upload media -> asynchronous job enqueue -> Demucs inference -> stem verification -> ZIP download -> IDOR protection -> project deletion.

---

## API Contract

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/uploads` | Upload media file, validate with `ffprobe`, extract metadata |
| `POST` | `/api/v1/separations` | Dispatch asynchronous AI separation job (`two_stem` / `four_stem`) |
| `GET` | `/api/v1/separations/{job_id}` | Retrieve job status, stage, progress, and stem outputs |
| `GET` | `/api/v1/separations/{job_id}/events` | Server-Sent Events (SSE) live progress stream |
| `GET` | `/api/v1/separations/{job_id}/stems` | List generated stems with signed download URLs |
| `GET` | `/api/v1/separations/{job_id}/download-zip` | Stream streaming ZIP archive of all isolated stems |
| `GET` | `/api/v1/stems/{stem_id}/download` | Download individual stem audio file (WAV) |
| `GET` | `/api/v1/stems/{stem_id}/stream` | Stream stem audio for browser Web Audio API |
| `GET` | `/api/v1/projects` | List historical projects (paginated) |
| `GET` | `/api/v1/projects/{project_id}` | Get project details, separations, and original stream URL |
| `DELETE`| `/api/v1/projects/{project_id}` | Delete project and permanently purge audio files from disk |
| `GET` | `/api/v1/health` | Basic liveness probe |
| `GET` | `/api/v1/readiness` | Deep readiness probe (DB, Redis, Storage, AI Model) |

---

## License

This project is licensed under the [MIT License](LICENSES.md).
Demucs v4 is developed by Meta AI Research and distributed under the MIT License.
