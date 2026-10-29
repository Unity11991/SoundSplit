from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from app.schemas.separation import SeparationResponseSchema

class ProjectResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    name: str
    original_filename: str
    original_url: str
    duration_seconds: float
    sample_rate: int
    channels: int
    format: str
    file_size_bytes: int
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    separations: List[SeparationResponseSchema] = []

class ProjectListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    original_filename: str
    duration_seconds: float
    format: str
    file_size_bytes: int
    status: str
    created_at: datetime
    separation_count: int = 0
    latest_separation_mode: Optional[str] = None
    latest_separation_status: Optional[str] = None
