export type SeparationMode = 'two_stem' | 'four_stem';

export type JobStatus = 
  | 'queued'
  | 'uploading'
  | 'validating'
  | 'processing'
  | 'finalizing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired';

export type StemType = 'vocals' | 'instrumental' | 'drums' | 'bass' | 'other';

export interface AudioMetadata {
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  format: string;
  file_size_bytes: number;
}

export interface StemInfo {
  id: string;
  separation_id: string;
  stem_type: StemType;
  filename: string;
  download_url: string;
  file_size_bytes: number;
  duration_seconds: number;
  sample_rate: number;
  format: string;
}

export interface SeparationJob {
  id: string;
  project_id: string;
  mode: SeparationMode;
  model_name: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error_code?: string | null;
  error_message?: string | null;
  processing_time_seconds?: number | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  stems: StemInfo[];
}

export interface Project {
  id: string;
  session_id: string;
  name: string;
  original_filename: string;
  original_url: string;
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  format: string;
  file_size_bytes: number;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  expires_at?: string | null;
  separations: SeparationJob[];
}

export interface UploadResponse {
  project_id: string;
  filename: string;
  metadata: AudioMetadata;
  upload_url?: string;
  status: string;
}

export interface CreateSeparationRequest {
  project_id: string;
  mode: SeparationMode;
  model_name?: string;
}

export interface JobEventPayload {
  job_id: string;
  project_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  error_message?: string | null;
  stems?: StemInfo[];
}
