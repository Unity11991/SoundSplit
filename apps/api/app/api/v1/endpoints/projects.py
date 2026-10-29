import os
import json
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_or_create_session_id, verify_project_ownership
from app.models.database import ProjectModel, SeparationModel, StemModel
from app.schemas.project import ProjectResponseSchema, ProjectListItemSchema
from app.schemas.common import PaginatedResponse
from app.services.storage import storage_service
from app.services.cleanup_service import storage_cleanup_service
from app.api.v1.endpoints.separations import _format_stem_response

router = APIRouter()

@router.get("/projects", response_model=PaginatedResponse[ProjectListItemSchema])
def list_projects(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List recent audio separation projects belonging to the current user/session."""
    session_id = get_or_create_session_id(request, response)
    
    query = db.query(ProjectModel).filter(ProjectModel.session_id == session_id)
    total = query.count()
    projects = query.order_by(ProjectModel.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    items = []
    for p in projects:
        latest_sep = p.separations[0] if p.separations else None
        items.append(ProjectListItemSchema(
            id=p.id,
            name=p.name,
            original_filename=p.original_filename,
            duration_seconds=p.duration_seconds,
            format=p.format,
            file_size_bytes=p.file_size_bytes,
            status=p.status,
            created_at=p.created_at,
            separation_count=len(p.separations),
            latest_separation_mode=latest_sep.mode if latest_sep else None,
            latest_separation_status=latest_sep.status if latest_sep else None
        ))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=(page * limit) < total
    )

@router.get("/projects/{project_id}", response_model=ProjectResponseSchema)
def get_project(
    project_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Get project details including all separations and stems."""
    session_id = get_or_create_session_id(request, response)
    
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    verify_project_ownership(project.session_id, session_id)

    base_url = str(request.base_url).rstrip("/")
    token = storage_service.generate_signed_token(project.original_storage_key)
    original_url = f"/api/v1/projects/{project.id}/original?token={token}"

    separations = []
    for s in project.separations:
        stems = [_format_stem_response(stem, base_url) for stem in s.stems]
        separations.append({
            "id": s.id,
            "project_id": s.project_id,
            "mode": s.mode,
            "model_name": s.model_name,
            "status": s.status,
            "progress": s.progress,
            "stage": s.stage,
            "error_code": s.error_code,
            "error_message": s.error_message,
            "processing_time_seconds": s.processing_time_seconds,
            "created_at": s.created_at,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
            "stems": stems
        })

    return ProjectResponseSchema(
        id=project.id,
        session_id=project.session_id,
        name=project.name,
        original_filename=project.original_filename,
        original_url=original_url,
        duration_seconds=project.duration_seconds,
        sample_rate=project.sample_rate,
        channels=project.channels,
        format=project.format,
        file_size_bytes=project.file_size_bytes,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        expires_at=project.expires_at,
        separations=separations
    )

@router.delete("/projects/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(
    project_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Delete project and permanently remove all audio storage assets."""
    session_id = get_or_create_session_id(request, response)
    
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    verify_project_ownership(project.session_id, session_id)

    # Thoroughly delete all input, output, transcode, and preview files
    storage_cleanup_service.delete_project_assets(project, db)

    # Delete from DB (cascades to separations and stems)
    db.delete(project)
    db.commit()

    return {"success": True, "message": f"Project '{project.name}' and all associated audio stems were deleted."}

@router.get("/projects/{project_id}/original")
def stream_original_audio(
    project_id: str,
    request: Request,
    response: Response,
    token: Optional[str] = Query(default=None),
    preview: bool = Query(default=True),
    db: Session = Depends(get_db)
):
    """Stream original audio track for playback and A/B comparison."""
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    session_id = get_or_create_session_id(request, response)
    
    # Verify either valid signed token or session ownership
    has_valid_token = token and storage_service.verify_signed_token(project.original_storage_key, token)
    if not has_valid_token:
        verify_project_ownership(project.session_id, session_id)

    file_path = storage_service.get_absolute_path(project.original_storage_key)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found on disk")

    if preview:
        import subprocess
        preview_path = file_path.with_suffix(".preview.mp3")
        if not preview_path.exists():
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(file_path), "-b:a", "256k", str(preview_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30
                )
            except Exception:
                pass
        if preview_path.exists():
            return FileResponse(
                path=preview_path,
                media_type="audio/mpeg",
                filename=f"{Path(project.original_filename).stem}.mp3"
            )

    media_type = f"audio/{project.format}" if project.format in ["wav", "mp3", "ogg", "flac"] else "audio/wav"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=project.original_filename
    )

@router.get("/projects/{project_id}/peaks")
def get_project_waveform_peaks(
    project_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Retrieve pre-computed waveform amplitude peaks for responsive mixer display."""
    session_id = get_or_create_session_id(request, response)
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    verify_project_ownership(project.session_id, session_id)

    # Check if latest separation has peaks JSON
    if project.separations:
        latest_sep = project.separations[0]
        peaks_file = storage_service.get_absolute_path(f"outputs/{latest_sep.id}/waveform_peaks.json")
        if peaks_file.exists():
            with open(peaks_file, "r") as f:
                return json.load(f)

    return {}
