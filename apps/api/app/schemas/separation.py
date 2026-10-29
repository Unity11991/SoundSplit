from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class CreateSeparationRequest(BaseModel):
    project_id: str = Field(..., description="ID of the uploaded audio project")
    mode: str = Field(default="two_stem", description="'two_stem', 'four_stem', or 'voiceover'")
    model_name: Optional[str] = Field(default="htdemucs", description="Name of the model to use")

class StemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    separation_id: str
    stem_type: str
    filename: str
    download_url: str
    stream_url: str
    file_size_bytes: int
    duration_seconds: float
    sample_rate: int
    format: str

class SeparationResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    mode: str
    model_name: str
    status: str
    progress: int
    stage: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stems: List[StemResponseSchema] = []
