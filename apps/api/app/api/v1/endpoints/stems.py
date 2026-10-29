import re
import urllib.parse
import subprocess
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_or_create_session_id, verify_project_ownership
from app.models.database import StemModel
from app.services.storage import storage_service

router = APIRouter()

def _sanitize_filename(raw_name: str, stem_type: str, ext: str = "mp3") -> tuple[str, str]:
    """
    Produce clean, safe, and universal filenames compatible with all mobile & desktop operating systems.
    Returns: (utf8_filename, ascii_fallback_filename)
    """
    if stem_type in ("vocals", "voiceover"):
        label = "Foreground_Speech"
    elif stem_type in ("background_music", "instrumental"):
        label = "Background_Music"
    else:
        label = stem_type.capitalize()

    # 1. Clean UTF-8 filename preserving Unicode characters (Japanese, Chinese, Hindi, etc.)
    # Strip characters illegal in Windows/macOS/Linux filenames and control chars
    clean_utf8 = re.sub(r'[\\/*?:"<>|\r\n\t\x00-\x1f]', '', raw_name).strip()
    clean_utf8 = re.sub(r'[-\s]+', '_', clean_utf8)
    if not clean_utf8:
        clean_utf8 = "SoundSplit"
    clean_utf8 = clean_utf8[:50]
    utf8_filename = f"{clean_utf8}_{label}.{ext}"

    # 2. Strict US-ASCII fallback (strictly printable ASCII without quotes/backslashes)
    clean_ascii = re.sub(r'[^a-zA-Z0-9]', '_', raw_name)
    clean_ascii = re.sub(r'_+', '_', clean_ascii).strip('_')
    if not clean_ascii:
        clean_ascii = "SoundSplit"
    clean_ascii = clean_ascii[:35]
    ascii_filename = f"{clean_ascii}_{label}.{ext}"

    return utf8_filename, ascii_filename

@router.get("/stems/{stem_id}/download")
def download_stem(
    stem_id: str,
    request: Request,
    response: Response,
    token: Optional[str] = Query(default=None),
    format: str = Query(default="mp3"),
    db: Session = Depends(get_db)
):
    """
    Download an isolated stem file.
    Defaults to 320kbps MP3 for 100% universal compatibility across all mobile phones,
    tablets, WhatsApp, and audio players, or lossless WAV if format=wav is specified.
    """
    stem = db.query(StemModel).filter(StemModel.id == stem_id).first()
    if not stem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stem not found")

    session_id = get_or_create_session_id(request, response)
    
    # Verify signed token or session ownership
    has_valid_token = token and storage_service.verify_signed_token(stem.storage_key, token)
    if not has_valid_token:
        verify_project_ownership(stem.separation.project.session_id, session_id)

    wav_file_path = storage_service.get_absolute_path(stem.storage_key)
    if not wav_file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stem file missing on disk")

    project_name = stem.separation.project.name or "SoundSplit"
    target_format = "wav" if format.lower() == "wav" else "mp3"
    utf8_filename, ascii_filename = _sanitize_filename(project_name, stem.stem_type, target_format)
    quoted_filename = urllib.parse.quote(utf8_filename, encoding="utf-8")
    content_disposition = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quoted_filename}'

    if target_format == "mp3":
        # Generate 320kbps MP3 with full universal compatibility
        mp3_path = wav_file_path.with_suffix(".320k.mp3")
        if not mp3_path.exists():
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(wav_file_path),
                        "-vn", "-b:a", "320k", "-codec:a", "libmp3lame",
                        str(mp3_path)
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30
                )
            except Exception as e:
                mp3_path = wav_file_path

        serve_path = mp3_path if mp3_path.exists() else wav_file_path
        media_type = "audio/mpeg" if serve_path.suffix.lower() == ".mp3" else "audio/wav"
    else:
        serve_path = wav_file_path
        media_type = "audio/wav"

    return FileResponse(
        path=serve_path,
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition,
            "Content-Type": media_type,
            "Accept-Ranges": "bytes"
        }
    )


@router.get("/stems/{stem_id}/stream")
def stream_stem(
    stem_id: str,
    request: Request,
    response: Response,
    token: Optional[str] = Query(default=None),
    preview: bool = Query(default=True),
    db: Session = Depends(get_db)
):
    """
    Stream stem audio for browser Web Audio API playback.
    When preview=True, streams high-bitrate 256kbps MP3 (cached) for 5x-10x faster loading over networks.
    """
    stem = db.query(StemModel).filter(StemModel.id == stem_id).first()
    if not stem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stem not found")

    session_id = get_or_create_session_id(request, response)
    
    has_valid_token = token and storage_service.verify_signed_token(stem.storage_key, token)
    if not has_valid_token:
        verify_project_ownership(stem.separation.project.session_id, session_id)

    file_path = storage_service.get_absolute_path(stem.storage_key)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stem file missing on disk")

    if preview:
        preview_path = file_path.with_suffix(".preview.mp3")
        if not preview_path.exists():
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(file_path), "-vn", "-b:a", "256k", "-codec:a", "libmp3lame", str(preview_path)],
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
                filename=f"{stem.stem_type}.mp3"
            )

    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=f"{stem.stem_type}.wav"
    )
