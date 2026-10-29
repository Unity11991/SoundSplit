export type SeparationMode = 'two_stem' | 'four_stem' | 'voiceover';

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

export type StemType = 'vocals' | 'instrumental' | 'drums' | 'bass' | 'other' | 'voiceover' | 'background_song' | 'song_vocals' | 'background_music';

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
  stream_url: string;
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

export interface ProjectListItem {
  id: string;
  name: string;
  original_filename: string;
  duration_seconds: number;
  format: string;
  file_size_bytes: number;
  status: JobStatus;
  created_at: string;
  separation_count: number;
  latest_separation_mode?: SeparationMode | null;
  latest_separation_status?: JobStatus | null;
}

export interface PaginatedProjects {
  items: ProjectListItem[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface SystemReadiness {
  status: 'ready' | 'degraded';
  checks: {
    database: { status: string; type?: string; error?: string };
    queue: { status: string; mode: string; redis_connected: boolean };
    storage: { status: string; type: string; directory: string; writable: boolean };
    ai_engine: {
      status: string;
      model: string;
      torch_version: string;
      cuda_available: boolean;
      device: string;
      supported_modes: string[];
    };
  };
}
