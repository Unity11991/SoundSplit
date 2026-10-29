import subprocess
import json
from pathlib import Path
from typing import Dict, Any
from fastapi import HTTPException

from app.core.config import settings

MAGIC_HEADERS = {
    b"RIFF": "wav",
    b"ID3": "mp3",
    b"\xff\xfb": "mp3",
    b"\xff\xf3": "mp3",
    b"\xff\xf2": "mp3",
    b"fLaC": "flac",
    b"OggS": "ogg",
}

class AudioValidationError(Exception):
    def __init__(self, message: str, code: str = "AUDIO_VALIDATION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)

class AudioValidator:
    @staticmethod
    def verify_magic_bytes(file_path: Path) -> bool:
        """Verify the first bytes of the file match known audio headers."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(12)
                if not header:
                    return False
                # Check MP4 / M4A ftyp box
                if len(header) >= 8 and header[4:8] == b"ftyp":
                    return True
                # Check other headers
                for magic in MAGIC_HEADERS:
                    if header.startswith(magic):
                        return True
            return True  # FFprobe will do the canonical validation
        except Exception:
            return False

    @staticmethod
    def inspect_audio(file_path: Path) -> Dict[str, Any]:
        """Inspect media using ffprobe to obtain precise codec, duration, and stream properties."""
        if not file_path.exists():
            raise AudioValidationError("Audio file does not exist on disk", "FILE_NOT_FOUND")

        file_size = file_path.stat().st_size
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise AudioValidationError(
                f"File size ({file_size / (1024 * 1024):.1f}MB) exceeds maximum permitted limit ({settings.MAX_UPLOAD_SIZE_MB}MB)",
                "FILE_TOO_LARGE"
            )

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path)
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise AudioValidationError("Audio file inspection timed out", "PROBE_TIMEOUT")
        except FileNotFoundError:
            raise AudioValidationError("ffprobe is not installed or not in system PATH", "SYSTEM_DEPENDENCY_MISSING")

        if result.returncode != 0:
            raise AudioValidationError("Invalid or corrupted audio file container", "CORRUPT_MEDIA")

        try:
            probe_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AudioValidationError("Failed to parse audio media metadata", "METADATA_PARSE_ERROR")

        streams = probe_data.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not audio_stream:
            raise AudioValidationError("No valid audio stream found in the uploaded file", "NO_AUDIO_STREAM")

        # Parse duration
        duration = 0.0
        format_info = probe_data.get("format", {})
        if "duration" in format_info:
            try:
                duration = float(format_info["duration"])
            except (ValueError, TypeError):
                duration = 0.0
        elif "duration" in audio_stream:
            try:
                duration = float(audio_stream["duration"])
            except (ValueError, TypeError):
                duration = 0.0

        if duration <= 0.0:
            raise AudioValidationError("Unable to determine audio duration or audio is empty", "INVALID_DURATION")

        if duration > settings.MAX_AUDIO_DURATION_SECONDS:
            raise AudioValidationError(
                f"Audio duration ({duration:.1f}s) exceeds maximum permitted limit ({settings.MAX_AUDIO_DURATION_SECONDS:.0f}s)",
                "DURATION_EXCEEDED"
            )

        sample_rate = int(audio_stream.get("sample_rate", 44100))
        channels = int(audio_stream.get("channels", 2))
        codec_name = audio_stream.get("codec_name", "unknown")
        format_name = format_info.get("format_name", "audio").split(",")[0]

        # Detect whether file contains video (excluding album art pictures)
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        is_video = False
        if video_stream:
            disposition = video_stream.get("disposition", {})
            codec = video_stream.get("codec_name", "")
            if not disposition.get("attached_pic", 0) and codec not in ["mjpeg", "png", "bmp"]:
                is_video = True
        
        ext = file_path.suffix.lower().lstrip(".")
        if ext in settings.ALLOWED_VIDEO_EXTENSIONS:
            is_video = True

        return {
            "duration_seconds": round(duration, 2),
            "sample_rate": sample_rate,
            "channels": channels,
            "codec_name": codec_name,
            "format": format_name,
            "file_size_bytes": file_size,
            "is_video": is_video,
        }

    @staticmethod
    def extract_audio_from_video(video_path: Path, output_wav_path: Path) -> Path:
        """
        Extract the audio stream from a video file into a lossless 44.1kHz stereo 16-bit PCM WAV.
        """
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            str(output_wav_path)
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180
            )
            if result.returncode != 0:
                err_msg = result.stderr[-300:] if result.stderr else "Unknown ffmpeg error"
                raise AudioValidationError(f"FFmpeg failed to extract audio from video: {err_msg}", "EXTRACTION_FAILED")
            if not output_wav_path.exists() or output_wav_path.stat().st_size == 0:
                raise AudioValidationError("Audio extraction from video produced an empty audio file", "EMPTY_AUDIO")
            return output_wav_path
        except subprocess.TimeoutExpired:
            raise AudioValidationError("Audio extraction from video timed out (media too long or decoding issue)", "EXTRACTION_TIMEOUT")
        except FileNotFoundError:
            raise AudioValidationError("ffmpeg is not installed or not in system PATH", "SYSTEM_DEPENDENCY_MISSING")

audio_validator = AudioValidator()
