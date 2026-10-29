# SoundSplit AI — Production Deployment Guide

Deploy SoundSplit with:
- **Backend (FastAPI + AI Inference)** on **[Render](https://render.com)**
- **Frontend (Next.js Studio)** on **[Vercel](https://vercel.com)**

---

## Architecture Overview

```
 ┌───────────────────────────┐           Direct API Calls & SSE           ┌────────────────────────────┐
 │      Vercel Frontend      │ ─────────────────────────────────────────> │       Render Backend       │
 │   https://your-app.vercel │ <───────────────────────────────────────── │ https://your-api.onrender  │
 └───────────────────────────┘            Audio Streams & Downloads       └────────────────────────────┘
               │                                                                        │
    • Next.js 16 Web Studio                                                  • FastAPI REST API
    • Interactive Waveforms                                                  • Demucs v4 Neural Engine
    • Cross-Origin Session Header                                            • Meta Denoiser DNS64
    • Bypasses Vercel 4.5MB limit                                            • FFmpeg Audio Processing
```

---

## Part 1: Deploy Backend on Render

### Step 1: Push Code to GitHub
Ensure your repository is pushed to your GitHub or GitLab account:
```bash
git add .
git commit -m "Configure Render and Vercel production hosting"
git push origin main
```

### Step 2: Create Service on Render
1. Go to your **[Render Dashboard](https://dashboard.render.com)**.
2. Click **New +** > **Web Service**.
3. Connect your GitHub repository.
4. Render will detect the configuration:
   - **Name**: `soundsplit-api` (or your preferred name)
   - **Language / Runtime**: **Docker**
   - **Dockerfile Path**: `./Dockerfile` (or `./infrastructure/docker/Dockerfile.api`)
   - **Docker Context**: `.`
   - **Region**: Choose the region closest to you or your users (e.g., Oregon, Frankfurt, Singapore).

> [!IMPORTANT]
> **Plan Selection (Memory Requirement)**:
> Select the **Starter Plan (2 GB RAM)**.
> PyTorch and the Demucs AI neural network require approximately **1.2 GB – 1.6 GB RAM** during active stem separation. The Render Free tier (512 MB) will terminate with an Out-of-Memory (OOM) error when running AI audio inference.

### Step 3: Configure Environment Variables
In the Render Web Service settings, navigate to **Environment** and add:

| Key | Recommended Value | Description |
|---|---|---|
| `PORT` | `8000` | Port uvicorn binds to (Render sets this dynamically) |
| `CORS_ORIGINS` | `*` | Or your Vercel URL `https://your-app.vercel.app` |
| `MAX_UPLOAD_SIZE_MB` | `100` | Maximum upload size per file (in MB) |
| `MAX_AUDIO_DURATION_SECONDS` | `600` | Maximum audio duration (10 minutes) |
| `RETENTION_HOURS` | `24` | Auto-cleanup period for temporary audio files |
| `SECRET_KEY` | *(Click "Generate")* | Cryptographic signing secret |

### Step 4: Deploy & Copy Backend URL
1. Click **Create Web Service**.
2. Render will build the Docker image (pre-downloading the Demucs model weights for fast startup).
3. Once the build completes and health check passes (`/api/v1/health`), copy your Render URL:
   `https://soundsplit-api.onrender.com`

---

## Part 2: Deploy Frontend on Vercel

### Step 1: Import Repository to Vercel
1. Go to your **[Vercel Dashboard](https://vercel.com/dashboard)**.
2. Click **Add New...** > **Project**.
3. Select your GitHub repository and click **Import**.

### Step 2: Configure Monorepo Root Directory
In the Vercel project configuration screen:
1. Locate **Root Directory** and click **Edit**.
2. Select or enter:
   ```
   apps/web
   ```
3. Click **Continue**.

### Step 3: Set Build & Framework Settings
- **Framework Preset**: Next.js (automatically detected)
- **Build Command**: `npm run build`
- **Output Directory**: `.next`
- **Install Command**: `npm install`

### Step 4: Add Environment Variable
Under **Environment Variables**, add:

| Key | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://soundsplit-api.onrender.com` | Your live Render backend URL from Part 1 |

> [!TIP]
> Ensure there is **no trailing slash** at the end of the URL.

### Step 5: Deploy
1. Click **Deploy**.
2. Vercel will install dependencies and compile the production Next.js bundle.
3. Once finished, click **Visit** to open your live application!

---

## Part 3: Verification Checklist

1. **Direct Upload**: Drag & drop an MP3/WAV/video file on the Vercel app. Verify that upload progress increments smoothly.
2. **Real-time SSE Progress**: Ensure the progress bar animates with stage updates (e.g. `Initializing AI neural network` -> `Running deep source separation` -> `Voice Enhancement & Studio Noise Cleanup`).
3. **Audio Playback**: Verify that the interactive waveform mixer plays both the Spoken Voiceover and Background Music tracks.
4. **Download**: Click the **Download (MP3)** button to download your separated stems with clean filenames.

---

## Alternative: One-Click Render Blueprint (`render.yaml`)

If you prefer deploying via Render Blueprint:
1. In Render Dashboard, click **New +** > **Blueprint**.
2. Select your repository.
3. Render will read [`render.yaml`](file:///f:/CodeEthicHack/AIVocal-Remover/render.yaml) from the root and configure the web service, health checks, and environment variables automatically.
