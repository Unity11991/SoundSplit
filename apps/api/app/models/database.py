import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship

from app.core.database import Base

def generate_uuid() -> str:
    return uuid.uuid4().hex

class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    original_storage_key = Column(String(512), nullable=False)
    file_size_bytes = Column(BigInteger, default=0)
    duration_seconds = Column(Float, default=0.0)
    sample_rate = Column(Integer, default=44100)
    channels = Column(Integer, default=2)
    format = Column(String(32), default="wav")
    status = Column(String(32), default="uploading", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)

    separations = relationship("SeparationModel", back_populates="project", cascade="all, delete-orphan", order_by="desc(SeparationModel.created_at)")

class SeparationModel(Base):
    __tablename__ = "separations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String(32), default="two_stem", nullable=False)
    model_name = Column(String(64), default="htdemucs", nullable=False)
    status = Column(String(32), default="queued", index=True, nullable=False)
    progress = Column(Integer, default=0)
    stage = Column(String(128), default="Queued in processing engine")
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("ProjectModel", back_populates="separations")
    stems = relationship("StemModel", back_populates="separation", cascade="all, delete-orphan")

class StemModel(Base):
    __tablename__ = "stems"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    separation_id = Column(String(36), ForeignKey("separations.id", ondelete="CASCADE"), nullable=False, index=True)
    stem_type = Column(String(32), nullable=False)  # vocals, instrumental, drums, bass, other
    storage_key = Column(String(512), nullable=False)
    file_size_bytes = Column(BigInteger, default=0)
    duration_seconds = Column(Float, default=0.0)
    sample_rate = Column(Integer, default=44100)
    format = Column(String(16), default="wav")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    separation = relationship("SeparationModel", back_populates="stems")
