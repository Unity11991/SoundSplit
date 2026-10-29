import io
import json
import zipfile
import re
import urllib.parse
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_or_create_session_id, verify_project_ownership
from app.models.database import ProjectModel, SeparationModel, StemModel
from app.schemas.separation import CreateSeparationRequest, SeparationResponseSchema, StemResponseSchema
from app.services.storage import storage_service
from app.services.queue_service import queue_service

router = APIRouter()

def _format_stem_response(stem: StemModel, base_url: str = "") -> StemResponseSchema:
    token = storage_service.generate_signed_token(stem.storage_key)
    download_url = f"/api/v1/stems/{stem.id}/download?token={token}"
    stream_url = f"/api/v1/stems/{stem.id}/stream?token={token}"
    return StemResponseSchema(
        id=stem.id,
        separation_id=stem.separation_id,
        stem_type=stem.stem_type,
        filename=f"{stem.stem_type}.{stem.format}",
        download_url=download_url,
        stream_url=stream_url,
        file_size_bytes=stem.file_size_bytes,
        duration_seconds=stem.duration_seconds,
        sample_rate=stem.sample_rate,
        format=stem.format
    )

@router.post("/separations", response_model=SeparationResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_separation(
    payload: CreateSeparationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Create a new asynchronous AI source separation job.
    Supports 'two_stem' (vocals, instrumental) and 'four_stem' (vocals, drums, bass, other).
    """
    session_id = get_or_create_session_id(request, response)
    
    project = db.query(ProjectModel).filter(ProjectModel.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    verify_project_ownership(project.session_id, session_id)

    if payload.mode not in ["two_stem", "four_stem", "voiceover"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid separation mode. Must be 'two_stem', 'four_stem', or 'voiceover'"
        )

    # Create Separation Job record
    job = SeparationModel(
        project_id=project.id,
        mode=payload.mode,
        model_name=payload.model_name or settings.DEFAULT_MODEL,
        status="queued",
        progress=0,
        stage="Queued for AI inference"
    )
    db.add(job)
    project.status = "queued"
    db.commit()
    db.refresh(job)

    # Enqueue job to background worker
    job_payload = {
        "job_id": job.id,
        "project_id": project.id,
        "mode": job.mode,
        "model_name": job.model_name
    }
    await queue_service.enqueue_job(job_payload)

    base_url = str(request.base_url).rstrip("/")
    return SeparationResponseSchema(
        id=job.id,
        project_id=job.project_id,
        mode=job.mode,
        model_name=job.model_name,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        error_code=job.error_code,
        error_message=job.error_message,
        processing_time_seconds=job.processing_time_seconds,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        stems=[]
    )

@router.get("/separations/{job_id}", response_model=SeparationResponseSchema)
def get_separation(
    job_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Get status, progress, stage, and outputs of a separation job."""
    session_id = get_or_create_session_id(request, response)
    
    job = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Separation job not found")

    verify_project_ownership(job.project.session_id, session_id)

    base_url = str(request.base_url).rstrip("/")
    stems = [_format_stem_response(s, base_url) for s in job.stems]

    return SeparationResponseSchema(
        id=job.id,
        project_id=job.project_id,
        mode=job.mode,
        model_name=job.model_name,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        error_code=job.error_code,
        error_message=job.error_message,
        processing_time_seconds=job.processing_time_seconds,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        stems=stems
    )

@router.get("/separations/{job_id}/events")
async def get_separation_events(
    job_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) streaming endpoint for live job progress and stage updates.
    """
    session_id = get_or_create_session_id(request, response)
    job = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    verify_project_ownership(job.project.session_id, session_id)

    async def event_generator():
        # First send the initial current state
        initial_event = {
            "job_id": job.id,
            "project_id": job.project_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "error_message": job.error_message
        }
        yield f"data: {json.dumps(initial_event)}\n\n"

        if job.status in ["completed", "failed", "cancelled"]:
            return

        async for event in queue_service.subscribe_events(job_id):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ["completed", "failed", "cancelled"]:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/separations/{job_id}/stems", response_model=List[StemResponseSchema])
def get_separation_stems(
    job_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """List stems generated for a separation job with streaming/download URLs."""
    session_id = get_or_create_session_id(request, response)
    job = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    verify_project_ownership(job.project.session_id, session_id)

    base_url = str(request.base_url).rstrip("/")
    return [_format_stem_response(s, base_url) for s in job.stems]

@router.get("/separations/{job_id}/download-zip")
def download_all_stems_zip(
    job_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Stream a ZIP archive containing all isolated stems for the separation job."""
    session_id = get_or_create_session_id(request, response)
    job = db.query(SeparationModel).filter(SeparationModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    verify_project_ownership(job.project.session_id, session_id)

    if job.status != "completed" or not job.stems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Separation stems are not ready for download")

    # 1. Clean UTF-8 and ASCII fallback filenames for the ZIP archive
    clean_utf8 = re.sub(r'[\\/*?:"<>|\r\n\t\x00-\x1f]', '', job.project.name).strip()
    clean_utf8 = re.sub(r'[-\s]+', '_', clean_utf8)
    if not clean_utf8:
        clean_utf8 = "SoundSplit"
    clean_utf8 = clean_utf8[:50]
    utf8_zip_filename = f"{clean_utf8}_stems_{job.mode}.zip"

    clean_ascii = re.sub(r'[^a-zA-Z0-9]', '_', job.project.name)
    clean_ascii = re.sub(r'_+', '_', clean_ascii).strip('_')
    if not clean_ascii:
        clean_ascii = "SoundSplit"
    clean_ascii = clean_ascii[:35]
    ascii_zip_filename = f"{clean_ascii}_stems_{job.mode}.zip"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for stem in job.stems:
            stem_path = storage_service.get_absolute_path(stem.storage_key)
            if stem_path.exists():
                arcname = f"{clean_ascii}_{stem.stem_type}.wav"
                zf.write(stem_path, arcname=arcname)

    zip_buffer.seek(0)
    quoted_zip_filename = urllib.parse.quote(utf8_zip_filename, encoding="utf-8")
    content_disposition = f'attachment; filename="{ascii_zip_filename}"; filename*=UTF-8\'\'{quoted_zip_filename}'

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(zip_buffer.getbuffer().nbytes)
        }
    )

