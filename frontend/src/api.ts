export interface Health {
  status: string
  models_ready: boolean
  auth_required: boolean
  authenticated?: boolean
}

export interface Media {
  id: string
  kind: 'photo' | 'video'
  original_name: string
  width: number
  height: number
  duration: number | null
  fps: number | null
  has_audio: boolean | null
  created_at: number
  url: string
  thumbnail_url: string | null
}

export interface Face {
  id: string
  index: number
  bbox: [number, number, number, number]
  score: number
}

export interface FaceDetection {
  t: number
  width: number
  height: number
  faces: Face[]
}

export type JobType = 'photo' | 'preview' | 'video'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Job {
  id: string
  type: JobType
  status: JobStatus
  progress: number
  message: string | null
  stats: Record<string, number> | null
  params: { target_media_id: string; t?: number; [key: string]: unknown }
  created_at: number
  started_at: number | null
  finished_at: number | null
  result_url: string | null
}

export interface ProgressEvent {
  type: 'progress'
  job_id: string
  progress: number
  fps: number | null
  eta_s: number | null
  frames_done: number
  frames_total: number
}

export interface JobPayload {
  type: JobType
  source_face_id: string
  target_media_id: string
  target_face_ids: string[] | 'all'
  enhance?: boolean
  watermark?: boolean
  similarity_threshold?: number
  t?: number
  trim?: { start: number; end: number }
  downscale_720p?: boolean
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch {
    throw new ApiError(0, 'Serveur injoignable.')
  }
  if (res.status === 401) onUnauthorized?.()
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : `Requête invalide (${res.status})`
    throw new ApiError(res.status, detail)
  }
  return body as T
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const api = {
  health: () => request<Health>('/api/health'),
  uploadMedia(file: File) {
    const body = new FormData()
    body.append('file', file)
    return request<Media>('/api/media', { method: 'POST', body })
  },
  detectFaces: (id: string, t = 0) => request<FaceDetection>(`/api/media/${id}/faces?t=${t}`, { method: 'POST' }),
  frameUrl: (id: string, t: number) => `/api/media/${id}/frame?t=${t}`,
  createJob: (payload: JobPayload) => request<Job>('/api/jobs', json('POST', payload)),
  listJobs: () => request<{ items: Job[] }>('/api/jobs'),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: 'DELETE' }),
  login: (password: string) => request<void>('/api/login', json('POST', { password })),
  logout: () => request<void>('/api/logout', { method: 'POST' }),
}
