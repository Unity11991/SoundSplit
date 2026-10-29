from pydantic import BaseModel, ConfigDict
from typing import Optional

class AudioMetadataSchema(BaseModel):
    duration_seconds: float
    sample_rate: int
    channels: int
    format: str
    file_size_bytes: int

class UploadResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    filename: str
    metadata: AudioMetadataSchema
    status: str
    created_at: str
