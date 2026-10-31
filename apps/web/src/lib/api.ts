import { Project, PaginatedProjects, SeparationJob, SeparationMode, SystemReadiness } from '@/types';

/**
 * Resolves the API base endpoint.
 * When NEXT_PUBLIC_API_URL is configured (e.g. hosted on Vercel connecting to Render),
 * it returns the full backend URL, bypassing Vercel serverless body size limits and proxy timeouts.
 */
export function getApiBase(): string {
  if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) {
    const raw = process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '');
    return `${raw}/api/v1`;
  }
  return '/api/v1';
}

/**
 * Resolves full URL for audio streaming, download, and event endpoints.
 */
export function resolveApiUrl(path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) {
    const raw = process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '');
    return `${raw}${path.startsWith('/') ? '' : '/'}${path}`;
  }
  return path;
}

/**
 * Retrieves or initializes a cryptographically random session ID persisted in localStorage.
 * Ensures consistent project access and ownership in cross-origin hosting (Vercel <-> Render).
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return '';
  let sid = localStorage.getItem('soundsplit_session_id');
  if (!sid || sid.length < 16) {
    sid = Array.from(crypto.getRandomValues(new Uint8Array(24)))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    localStorage.setItem('soundsplit_session_id', sid);
  }
  return sid;
}

function getAuthHeaders(extraHeaders: Record<string, string> = {}): Record<string, string> {
  const sid = getSessionId();
  const headers: Record<string, string> = { ...extraHeaders };
  if (sid) {
    headers['X-Session-ID'] = sid;
  }
  return headers;
}

export async function uploadAudio(
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ project_id: string; filename: string; metadata: any }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    const uploadUrl = `${getApiBase()}/uploads`;
    xhr.open('POST', uploadUrl);
    xhr.withCredentials = true;

    const sid = getSessionId();
    if (sid) {
      xhr.setRequestHeader('X-Session-ID', sid);
    }

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          resolve(res);
        } catch (err) {
          reject(new Error('Invalid response from server'));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || 'Upload failed'));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(formData);
  });
}

export async function createSeparation(
  projectId: string,
  mode: SeparationMode = 'two_stem',
  modelName: string = 'htdemucs'
): Promise<SeparationJob> {
  const res = await fetch(`${getApiBase()}/separations`, {
    method: 'POST',
    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
    credentials: 'include',
    body: JSON.stringify({ project_id: projectId, mode, model_name: modelName }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start separation job');
  }

  return res.json();
}

export async function getSeparation(jobId: string): Promise<SeparationJob> {
  const res = await fetch(`${getApiBase()}/separations/${jobId}`, {
    headers: getAuthHeaders(),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to fetch separation status');
  }
  return res.json();
}

export function subscribeSeparationEvents(
  jobId: string,
  onEvent: (event: any) => void,
  onError?: (err: any) => void
): () => void {
  const sid = getSessionId();
  const sepUrl = resolveApiUrl(`/api/v1/separations/${jobId}/events${sid ? `?session_id=${sid}` : ''}`);
  const eventSource = new EventSource(sepUrl, { withCredentials: true });

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
      if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        eventSource.close();
      }
    } catch (err) {
      console.error('SSE JSON error:', err);
    }
  };

  eventSource.onerror = (err) => {
    if (onError) onError(err);
    eventSource.close();
  };

  return () => {
    eventSource.close();
  };
}

export async function getProject(projectId: string): Promise<Project> {
  const res = await fetch(`${getApiBase()}/projects/${projectId}`, {
    headers: getAuthHeaders(),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Project not found');
  }
  return res.json();
}

export async function listProjects(page = 1, limit = 20): Promise<PaginatedProjects> {
  const res = await fetch(`${getApiBase()}/projects?page=${page}&limit=${limit}`, {
    headers: getAuthHeaders(),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to list projects');
  }
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/projects/${projectId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error('Failed to delete project');
  }
}

export async function getReadiness(): Promise<SystemReadiness> {
  const res = await fetch(`${getApiBase()}/readiness`, {
    headers: getAuthHeaders(),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error('Failed to fetch system readiness');
  }
  return res.json();
}

export async function getProjectPeaks(projectId: string): Promise<Record<string, number[]>> {
  try {
    const res = await fetch(`${getApiBase()}/projects/${projectId}/peaks`, {
      headers: getAuthHeaders(),
      credentials: 'include',
      cache: 'no-store',
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.warn('Failed to load pre-rendered peaks:', e);
  }
  return {};
}

export async function getStorageStatus(): Promise<any> {
  const res = await fetch(`${getApiBase()}/storage/status`, {
    headers: getAuthHeaders(),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to get storage status');
  return res.json();
}

export async function triggerStorageCleanup(retentionHours?: number): Promise<any> {
  const url = retentionHours 
    ? `${getApiBase()}/storage/cleanup?retention_hours=${retentionHours}` 
    : `${getApiBase()}/storage/cleanup`;
  const res = await fetch(url, {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to run storage cleanup');
  return res.json();
}
