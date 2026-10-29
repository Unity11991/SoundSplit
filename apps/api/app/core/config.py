from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "SoundSplit"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./stemlab.db", description="PostgreSQL or SQLite connection string")
    
    # Redis & Asynchronous Queue
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL for queue and PubSub")
    REDIS_QUEUE_NAME: str = "stemlab:separations"
    
    # Storage Configuration
    STORAGE_TYPE: str = Field(default="local", description="'local' or 's3'")
    STORAGE_LOCAL_DIR: str = Field(default="./storage", description="Local storage root directory")
    S3_BUCKET: str = "stemlab-audio"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    
    # Limits & Constraints
    MAX_UPLOAD_SIZE_MB: int = Field(default=300, description="Max upload size in Megabytes (supports larger video files)")
    MAX_AUDIO_DURATION_SECONDS: float = Field(default=600.0, description="Max audio duration in seconds (10 mins)")
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [
        "wav", "mp3", "flac", "m4a", "aac", "ogg", "opus", "wma", "aiff", "aif"
    ]
    ALLOWED_VIDEO_EXTENSIONS: List[str] = [
        "mp4", "mkv", "mov", "avi", "webm", "flv", "m4v", "wmv", "ts"
    ]
    ALLOWED_EXTENSIONS: List[str] = [
        "wav", "mp3", "flac", "m4a", "aac", "ogg", "opus", "wma", "aiff", "aif",
        "mp4", "mkv", "mov", "avi", "webm", "flv", "m4v", "wmv", "ts"
    ]
    ALLOWED_MIME_TYPES: List[str] = [
        "audio/wav", "audio/x-wav", "audio/wave",
        "audio/mpeg", "audio/mp3",
        "audio/flac", "audio/x-flac",
        "audio/mp4", "audio/m4a", "audio/x-m4a",
        "audio/aac", "audio/ogg", "application/ogg",
        "video/mp4", "video/x-matroska", "video/quicktime",
        "video/x-msvideo", "video/webm", "video/x-flv",
        "video/x-m4v", "video/x-ms-wmv", "video/mp2t", "video/*"
    ]
    
    # Model & Separation Engine
    DEFAULT_MODEL: str = "htdemucs"
    DEFAULT_DEVICE: str = "auto"  # 'auto', 'cuda', 'cpu'
    DEMUCS_SEGMENT: int = 8  # segment duration in seconds for VRAM management
    DEMUCS_OVERLAP: float = 0.25
    DEMUCS_SHIFTS: int = 1  # 1 for faster inference, 2 for higher quality
    
    # Security & Auth
    SESSION_COOKIE_NAME: str = "stemlab_session"
    SECRET_KEY: str = Field(default="stemlab-super-secret-key-change-in-production-2026", description="Secret for signing tokens/URLs")
    SIGNED_URL_EXPIRATION_SECONDS: int = 3600  # 1 hour
    
    # Intelligent Storage Cleanup & Retention Policy
    RETENTION_HOURS: int = Field(default=24, description="Auto-expire and cleanup projects older than N hours")
    MAX_STORAGE_MB: int = Field(default=2048, description="Maximum storage folder size in MB before LRU eviction triggers")
    STORAGE_CLEANUP_INTERVAL_MINUTES: int = Field(default=30, description="Interval in minutes for background cleanup worker")
    AUTO_CLEAN_ORPHANS: bool = Field(default=True, description="Automatically clean unreferenced orphaned files in storage")
    ORPHAN_GRACE_PERIOD_MINUTES: int = Field(default=15, description="Do not touch newly modified files within grace period")
    FAILED_JOB_RETENTION_HOURS: int = Field(default=2, description="Clean up failed or stuck jobs older than N hours")
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="allow")

settings = Settings()
