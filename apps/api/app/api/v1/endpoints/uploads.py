from fastapi import APIRouter, UploadFile, File, Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_or_create_session_id
from app.models.database import ProjectModel
from app.services.storage import storage_service
from app.services.cleanup_service import storage_cleanup_service
from app.services.audio_validator import audio_validator, AudioValidationError
from app.schemas.upload import UploadResponseSchema, AudioMetadataSchema

router = APIRouter()

@router.post("/uploads", response_model=UploadResponseSchema, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload and validate raw audio media.
    Inspects media container with ffprobe, detects duration, sample rate, channels.
    """
    session_id = get_or_create_session_id(request, response)
    
    # 1. Validate file extension
    filename = file.filename or "audio.wav"
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # Proactively ensure disk capacity before storing incoming media
    try:
        storage_cleanup_service.ensure_upload_capacity(estimated_bytes=50 * 1024 * 1024)
    except Exception:
        pass

    # 2. Save uploaded file to secure temporary storage
    try:
        storage_key, file_path, file_size = storage_service.save_upload(file.file, filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    # 3. Deep media validation using FFprobe & magic bytes
    try:
        metadata = audio_validator.inspect_audio(file_path)
    except AudioValidationError as e:
        # Cleanup uploaded invalid file immediately
        storage_service.delete_file(storage_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except Exception as e:
        storage_service.delete_file(storage_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Audio validation failed: {str(e)}")

    # 4. Video Processing: If file is video, extract pristine 44.1kHz stereo audio track
    final_storage_key = storage_key
    if metadata.get("is_video"):
        try:
            wav_filename = f"{file_path.stem}_audio.wav"
            wav_storage_key = f"inputs/{wav_filename}"
            wav_path = storage_service.get_absolute_path(wav_storage_key)
            
            # Extract audio track to lossless 16-bit PCM WAV
            audio_validator.extract_audio_from_video(file_path, wav_path)
            
            # Inspect the extracted audio file for verified duration, sample rate, channels
            extracted_meta = audio_validator.inspect_audio(wav_path)
            metadata["duration_seconds"] = extracted_meta["duration_seconds"]
            metadata["sample_rate"] = extracted_meta["sample_rate"]
            metadata["channels"] = extracted_meta["channels"]
            metadata["format"] = "wav"
            metadata["file_size_bytes"] = extracted_meta["file_size_bytes"]
            
            final_storage_key = wav_storage_key
            # Remove bulky original video container to save disk space
            storage_service.delete_file(storage_key)
        except AudioValidationError as e:
            storage_service.delete_file(storage_key)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
        except Exception as e:
            storage_service.delete_file(storage_key)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to extract audio from video: {str(e)}")

    # 5. Create Project record in database with retention expiration
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.RETENTION_HOURS)
    project = ProjectModel(
        session_id=session_id,
        name=Path(filename).stem,
        original_filename=filename,
        original_storage_key=final_storage_key,
        file_size_bytes=metadata["file_size_bytes"],
        duration_seconds=metadata["duration_seconds"],
        sample_rate=metadata["sample_rate"],
        channels=metadata["channels"],
        format=metadata["format"],
        status="ready",
        expires_at=expires_at
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return UploadResponseSchema(
        project_id=project.id,
        filename=project.original_filename,
        metadata=AudioMetadataSchema(
            duration_seconds=project.duration_seconds,
            sample_rate=project.sample_rate,
            channels=project.channels,
            format=project.format,
            file_size_bytes=project.file_size_bytes
        ),
        status=project.status,
        created_at=project.created_at.isoformat()
    )
