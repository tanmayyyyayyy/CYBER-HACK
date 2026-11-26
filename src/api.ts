export type Clip = {
  id: string;
  filename: string;
  cameraId: string;
  sizeBytes: number;
  duration: number;
  width: number;
  height: number;
  fps: number;
  codec: string;
  playbackCodec: string;
  normalized: boolean;
  previewReady: boolean;
  sha256: string;
  uploadedAt: string;
  videoUrl: string;
  posterUrl: string;
};

export type Candidate = {
  id: string;
  analysisId: string;
  clipId: string;
  time: number;
  timeLabel: string;
  trackId: number;
  score: number;
  metrics: { sharpness: number; illumination: number; faceSize: number; pose: number; confidence: number };
  flags: string[];
  reviewStatus: 'unreviewed' | 'selected' | 'rejected';
  note: string;
  imageUrl: string;
};

export type Analysis = {
  id: string;
  clipId: string;
  clipName: string;
  transactionTime: string;
  transactionRef: string;
  timeMode: 'clip' | 'absolute';
  clipStartTime: string;
  windowSeconds: number;
  status: 'running' | 'completed' | 'failed' | 'queued';
  error: string;
  createdAt: string;
  result: {
    windowStart?: number;
    windowEnd?: number;
    sampledFrames?: number;
    peopleSeen?: number;
    candidateCount?: number;
    reviewNote?: string;
    models?: Record<string, string>;
  };
  candidates: Candidate[];
};

export type CameraSlot = { id: string; label: string; clips: Clip[]; status: string; source: string };
export type Health = { status: string; service: string; models: Record<string, string>; ffmpeg: boolean; cloud: string };
export type AuditItem = { id: string; action: string; subjectId: string; note: string; occurredAt: string };
export type AuditIntegrity = { verified: boolean; entriesChecked: number; headHash?: string; entryId?: string; reason?: string; limitation?: string };
export type EventItem = { id: string; kind: string; message: string; severity: string; occurredAt: string };
export type AuthUser = { id: string; email: string; displayName: string; role: 'administrator' | 'investigator'; status: string; createdAt: string };
export type LocalAccount = AuthUser & { approvedAt: string };
export type DatabaseBackup = { id: string; createdAt: string; sizeBytes: number; sha256: string; downloadUrl?: string; scope?: string };
export type SecurityOverview = {
  database: { integrity: string; foreignKeyViolations: number; sizeBytes: number; directoryPermissions: { restricted: boolean; mode: string }; filePermissions: { restricted: boolean; mode: string } };
  audit: AuditIntegrity;
  accounts: { active: number; pending: number; failedSignins24h: number };
  evidence: { clipCount: number; lastFullCheck: null | { checkedAt: string; clipsChecked: number; mismatchCount: number } };
  backup: DatabaseBackup | null;
  hostEncryption: { status: string; message: string };
  networkBoundary: { status: string; message: string };
};
let csrfToken = '';
export const setCsrfToken = (value: string) => { csrfToken = value; };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.method && !['GET', 'HEAD'].includes(init.method.toUpperCase()) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(path.startsWith('/api') ? path : `/api${path}`, { ...init, headers, credentials: 'same-origin' });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('drishti:session-expired'));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  authBootstrap: () => request<{ needsAdministrator: boolean }>('/auth/bootstrap'),
  authMe: async () => { const result = await request<{ user: AuthUser; csrfToken: string }>('/auth/me'); setCsrfToken(result.csrfToken); return result; },
  authLogin: async (email: string, password: string) => { const result = await request<{ user: AuthUser; csrfToken: string }>('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) }); setCsrfToken(result.csrfToken); return result; },
  authSignup: async (displayName: string, email: string, password: string) => { const result = await request<{ user: AuthUser; csrfToken: string | null; approvalRequired: boolean }>('/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName, email, password }) }); if (result.csrfToken) setCsrfToken(result.csrfToken); return result; },
  authLogout: async () => { await request<{ ok: boolean }>('/auth/logout', { method: 'POST' }); setCsrfToken(''); },
  accounts: () => request<LocalAccount[]>('/auth/users'),
  updateAccount: (id: string, status: 'active' | 'disabled') => request<AuthUser>(`/auth/users/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }),
  securityOverview: () => request<SecurityOverview>('/security/overview'),
  verifyAllEvidence: () => request<{ checked: number; verified: number; mismatches: { clipId: string; filename: string; sourceMatches: boolean; analysisMatches: boolean }[]; checkedAt: string; notice: string }>('/security/evidence-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clip_ids: [] }) }),
  databaseBackups: () => request<DatabaseBackup[]>('/security/database-backups'),
  createDatabaseBackup: (passphrase: string) => request<DatabaseBackup>('/security/database-backups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passphrase }) }),
  health: () => request<Health>('/health'),
  overview: () => request<{ clips: number; analyses: number; candidates: number; pending: number }>('/overview'),
  clips: () => request<Clip[]>('/clips'),
  cameras: () => request<CameraSlot[]>('/cameras'),
  analyses: () => request<Analysis[]>('/analyses'),
  analysis: (id: string) => request<Analysis>(`/analyses/${id}`),
  events: () => request<EventItem[]>('/events'),
  audit: () => request<AuditItem[]>('/audit'),
  auditIntegrity: () => request<AuditIntegrity>('/audit/integrity'),
  reports: () => request<{ analyses: Record<string, number>; reviews: Record<string, number>; quality: { average: number; best: number; lowest: number }; events: Record<string, number> }>('/reports'),
  upload: (file: File, cameraId: string) => request<Clip>(`/clips?filename=${encodeURIComponent(file.name)}&camera_id=${cameraId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
  }),
  analyze: (payload: { clip_id: string; transaction_time: string; time_mode: 'clip' | 'absolute'; clip_start_time: string; transaction_ref: string; window_seconds: number }) =>
    request<{ id: string; status: string }>('/analyses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  review: (id: string, status: Candidate['reviewStatus'], note: string) =>
    request(`/candidates/${id}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note }) }),
  search: (id: string) => request<{ matches: (Candidate & { similarity: number; filename: string })[]; notice: string }>('/search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: id }),
  }),
  deleteClip: (id: string) => request(`/clips/${id}`, { method: 'DELETE' }),
  integrity: (id: string) => request<{ verified: boolean; sourceMatches: boolean; analysisMatches: boolean; sourceSha256: string; analysisSha256: string; normalized: boolean; checkedAt: string; notice: string }>(`/clips/${id}/integrity`),
};

export const formatDuration = (seconds: number) => {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 3600)).padStart(2, '0')}:${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
};

export const formatBytes = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
