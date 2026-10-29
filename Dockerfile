# StemLab / SoundSplit AI — Backend API Dockerfile for Render / Cloud Deployments
FROM python:3.12-slim

# Install system dependencies including FFmpeg and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Demucs htdemucs model weights into image cache to prevent cold start delays
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

# Copy source code
COPY apps/api/app /app/app
COPY apps/worker /app/apps/worker
COPY packages /app/packages

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/storage/inputs /app/storage/outputs /app/storage/exports /home/appuser/.cache && \
    cp -r /root/.cache/* /home/appuser/.cache/ 2>/dev/null || true && \
    chown -R appuser:appuser /app /home/appuser

USER appuser

ENV PYTHONPATH=/app:/app/apps/worker:/app/app
ENV STORAGE_LOCAL_DIR=/app/storage
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
