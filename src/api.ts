export type ClipForensics = {
  container?: {
    probed?: boolean;
    formatName?: string;
    codecName?: string;
    pixFmt?: string;
    bitRateKbps?: number;
    nbFrames?: number;
    encoderTag?: string;
    cues?: string[];
  };
  continuity?: {
    checked?: boolean;
    sampled?: number;
    spliceCues?: number;
    blackoutFrames?: number;
    cues?: string[];
  };
};

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
  analysisSha256?: string;
  forensics?: ClipForensics;
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
  metrics: { sharpness: number; illumination: number; faceSize: number; pose: number; confidence: number; occlusionFree?: number };
  flags: string[];
  bbox?: number[];
  reviewStatus: 'unreviewed' | 'selected' | 'rejected';
  note: string;
  imageUrl: string;
  frameUrl: string;
  enhancedUrl: string;
  redactedFrameUrl: string;
};

export type AnalysisAlert = {
  kind: string;
  severity: string;
  message: string;
};

export type FaceEnhancement = { imageUrl: string; sources: Candidate[]; fused: boolean };

export type FaceVisibility = 'visible' | 'covered' | 'unavailable';
export type FootageObservation = {
  id: string;
  time: number;
  visibility: FaceVisibility;
  note: string;
  actorId: string;
  recordedAt: string;
  incident: { id: string; kind: string; occurred_at: string } | null;
};

export type Analysis = {
  id: string;
  clipId: string;
  clipName: string;
  cameraId?: string;
  transactionTime: string;
  transactionRef: string;
  transactionOffsetSeconds?: number | null;
  caseRef?: string;
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
    personFrames?: number;
    personWithoutFaceSamples?: number[];
    trackingEngine?: string;
    peopleSeen?: number;
    primaryTerminalTrack?: number | null;
    candidateCount?: number;
    embeddingModel?: string;
    alerts?: AnalysisAlert[];
    reviewNote?: string;
    models?: Record<string, string>;
  };
  candidates: Candidate[];
  observations?: FootageObservation[];
};

export type SurveillanceStream = {
  id: string;
  channelId: string;
  name: string;
  zone: string;
  status: string;
  sourceAdapter: string;
  sourceLabel: string;
  trackingEngine?: string;
  customSource?: string;
  resolvedSource?: string;
  lastError?: string;
  isLiveCamera?: boolean;
  sourceAvailable: boolean;
  personCount: number;
  faceCount?: number;
  activeTracks: number;
  fps: number;
  framesProcessed: number;
  alertState: 'clear' | 'active' | 'alert';
  securityStage?: 'clear' | 'observing_rule1' | 'alert_escalated';
  rule1Note?: string;
  lastAlert: string;
  watchlistHit?: string;
  repeatHit?: string;
  lastFrameAt: string;
  hasFaceCapture?: boolean;
  latestFaceScore?: number;
  latestFaceFlags?: string[];
  latestFaceAt?: string;
  latestFaceUrl?: string;
  mjpegUrl: string;
  snapshotUrl: string;
};

export type StreamsResponse = {
  running: boolean;
  detector: string;
  mode: string;
  notice: string;
  streams: SurveillanceStream[];
};

export type StreamDetection = {
  id: string;
  cameraId: string;
  trackId: number;
  personCount: number;
  confidence: number;
  alertKind: string;
  occurredAt: string;
  details: Record<string, unknown>;
};

export type JournalRow = {
  row: number;
  timestamp: string;
  txnRef: string;
  atmId: string;
  status: string;
  offsetSeconds: number;
  inClip: boolean;
  disputed: boolean;
  analysisId?: string;
};

export type CameraSlot = { id: string; label: string; clips: Clip[]; status: string; source: string };
export type Health = { status: string; service: string; models: Record<string, string>; ffmpeg: boolean; ffprobe?: boolean; cloud: string };
export type AuditItem = { id: string; action: string; subjectId: string; note: string; description?: string; actorId?: string | null; occurredAt: string; entryHash?: string };
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
  signingKey?: { present: boolean; permissions: { restricted: boolean; mode: string } };
  hostEncryption: { status: string; message: string };
  networkBoundary: { status: string; message: string };
};
export type WatchlistEntry = {
  id: string;
  label: string;
  caseRef: string;
  candidateId: string;
  clipId: string;
  createdAt: string;
  imageUrl: string;
};

export type LiveSighting = {
  id: string;
  cameraId: string;
  score: number;
  similarity: number;
  sha256: string;
  occurredAt: string;
  imageUrl: string;
};

export type LiveEvidenceSubject = {
  id: string;
  subjectCode: string;
  label: string;
  bestScore: number;
  bestSha256: string;
  firstCameraId: string;
  lastCameraId: string;
  cameras: string[];
  flags: string[];
  sightingCount: number;
  appearanceCount: number;
  isRepeat: boolean;
  firstSeenAt: string;
  lastSeenAt: string;
  imageUrl: string;
  sightings: LiveSighting[];
};

export type LiveEvidenceResponse = {
  summary: { totalSubjects: number; repeatSubjects: number; totalSightings: number };
  subjects: LiveEvidenceSubject[];
};

export type LiveIncident = {
  id: string;
  cameraId: string;
  kind: string;
  severity: string;
  summary: string;
  subjectCode: string;
  personCount: number;
  faceCount: number;
  sha256: string;
  occurredAt: string;
  imageUrl: string;
};

export type CaseDossier = {
  id: string;
  firNumber: string;
  ncrpAck: string;
  policeStation: string;
  ioName: string;
  ioBadge: string;
  atmId: string;
  bankName: string;
  fraudType: string;
  lossInr: number;
  notes: string;
  updatedAt: string;
};

export type CaseJourney = {
  readinessScore: number;
  auditVerified: boolean;
  channelsCovered: number;
  clipCount: number;
  completedAnalyses: number;
  selectedSuspects: number;
  bestFaceQuality: number;
  occlusionFlags: string[];
  watchlistCount: number;
  liveSubjects?: number;
  repeatSubjects?: number;
  alertCount: number;
  crossLinks: {
    sourceCamera: string;
    targetCamera: string;
    similarity: number;
    sourceCandidateId: string;
    targetCandidateId: string;
    targetAnalysisId: string;
  }[];
  timeline: {
    id: string;
    stage: string;
    cameraId: string;
    title: string;
    detail: string;
    timestamp: string;
    severity: string;
    analysisId?: string;
  }[];
  notice: string;
};

export type ReportsData = {
  analyses: Record<string, number>;
  reviews: Record<string, number>;
  quality: { average: number; best: number; lowest: number };
  events: Record<string, number>;
  flags?: Record<string, number>;
  streams?: Record<string, { events: number; detections: number }>;
};

let csrfToken = '';
export const setCsrfToken = (value: string) => { csrfToken = value; };
export const MAX_CLIP_BYTES = 500_000_000;

function errorDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const errors = detail.filter((item): item is { loc?: unknown; msg?: unknown; type?: unknown; ctx?: { min_length?: unknown } } => !!item && typeof item === 'object');
    const passwordError = errors.find((item) => Array.isArray(item.loc) && item.loc.includes('password') && item.type === 'string_too_short');
    if (passwordError && typeof passwordError.ctx?.min_length === 'number') {
      return `Password mein kam se kam ${passwordError.ctx.min_length} characters likhein.`;
    }
    const descriptions = errors.map((item) => typeof item.msg === 'string' ? item.msg : '').filter(Boolean);
    if (descriptions.length) return descriptions.join(' ');
  }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message;
  return `Request poori nahi hui (${status}). Di hui jankari check karein.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.method && !['GET', 'HEAD'].includes(init.method.toUpperCase()) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(path.startsWith('/api') ? path : `/api${path}`, { ...init, headers, credentials: 'same-origin' });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('drishti:session-expired'));
    throw new Error(errorDetail(payload.detail, response.status));
  }
  return response.json() as Promise<T>;
}

function uploadRequest(file: File, cameraId: string, replaceClipId: string, onProgress?: (percent: number) => void, signal?: AbortSignal): Promise<Clip> {
  if (file.size > MAX_CLIP_BYTES) return Promise.reject(new Error('Video 500 MB se bada hai. Chhota clip upload karein.'));
  if (signal?.aborted) return Promise.reject(new DOMException('Upload rok diya gaya.', 'AbortError'));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const path = `/api/clips?filename=${encodeURIComponent(file.name)}&camera_id=${encodeURIComponent(cameraId)}${replaceClipId ? `&replace_clip_id=${encodeURIComponent(replaceClipId)}` : ''}`;
    xhr.open('POST', path);
    xhr.withCredentials = true;
    xhr.timeout = 15 * 60 * 1000;
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    if (csrfToken) xhr.setRequestHeader('X-CSRF-Token', csrfToken);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable && event.total) onProgress?.(Math.round(event.loaded / event.total * 100)); };
    xhr.upload.onload = () => onProgress?.(100);
    xhr.onload = () => {
      const payload = (() => { try { return JSON.parse(xhr.responseText); } catch { return {}; } })();
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload as Clip);
      else {
        if (xhr.status === 401) window.dispatchEvent(new Event('drishti:session-expired'));
        reject(new Error(errorDetail(payload.detail, xhr.status)));
      }
    };
    xhr.onerror = () => reject(new Error('Server se connection nahi bana. Dobara koshish karein.'));
    xhr.ontimeout = () => reject(new Error('Video check mein bahut waqt lag gaya. Chhota clip upload karein.'));
    xhr.onabort = () => reject(new DOMException('Upload rok diya gaya.', 'AbortError'));
    const abort = () => xhr.abort();
    signal?.addEventListener('abort', abort, { once: true });
    xhr.onloadend = () => signal?.removeEventListener('abort', abort);
    if (signal?.aborted) xhr.abort();
    else xhr.send(file);
  });
}

export const api = {
  enhanceFaces: (candidateIds: string[]) => request<FaceEnhancement>('/face-enhancement', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_ids: candidateIds, same_person_confirmed: true }),
  }),
  authBootstrap: () => request<{ needsAdministrator: boolean; authenticated?: boolean }>('/auth/bootstrap'),
  authMe: async () => { const result = await request<{ user: AuthUser; csrfToken: string }>('/auth/me'); setCsrfToken(result.csrfToken); return result; },
  authLogin: async (email: string, password: string) => { const result = await request<{ user: AuthUser; csrfToken: string }>('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) }); setCsrfToken(result.csrfToken); return result; },
  authSignup: async (displayName: string, email: string, password: string) => { const result = await request<{ user: AuthUser; csrfToken: string | null; approvalRequired: boolean }>('/auth/signup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName, email, password }) }); if (result.csrfToken) setCsrfToken(result.csrfToken); return result; },
  authLogout: async () => { await request<{ ok: boolean }>('/auth/logout', { method: 'POST' }); setCsrfToken(''); },
  accounts: () => request<LocalAccount[]>('/auth/users'),
  updateAccount: (id: string, status: 'active' | 'disabled') => request<AuthUser>(`/auth/users/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }),
  securityOverview: () => request<SecurityOverview>('/security/overview'),
  verifyAllEvidence: () => request<{ checked: number; verified: number; mismatches: { clipId: string; filename: string; sourceMatches: boolean; analysisMatches: boolean }[]; checkedAt: string; notice: string }>('/security/evidence-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clip_ids: [] }) }),
  verifyManifest: (manifest: unknown) => request<{ verified: boolean; payloadSha256?: string; algorithm?: string; reason?: string }>('/security/verify-manifest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ manifest }) }),
  verifyBlockchainEvidence: (bundle: unknown) => request<{ verified: boolean; payloadSha256: string; blockNumber?: number; reason?: string }>('/security/verify-blockchain', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bundle) }),
  publishBlockchainEvidence: (analysisId: string) => request<{ manifest: unknown; transactionHash: string; chainId: string }>(`/evidence/${analysisId}/blockchain`, { method: 'POST' }),
  databaseBackups: () => request<DatabaseBackup[]>('/security/database-backups'),
  createDatabaseBackup: (passphrase: string) => request<DatabaseBackup>('/security/database-backups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passphrase }) }),
  health: () => request<Health>('/health'),
  dvrGuidance: () => request<{ supportedExtensions: string[]; guidance: { vendor: string; steps: string }[] }>('/dvr-guidance'),
  overview: () => request<{ clips: number; analyses: number; candidates: number; pending: number }>('/overview'),
  clips: () => request<Clip[]>('/clips'),
  cameras: () => request<CameraSlot[]>('/cameras'),
  analyses: () => request<Analysis[]>('/analyses'),
  analysis: (id: string) => request<Analysis>(`/analyses/${id}`),
  recordFootageObservation: (analysisId: string, observation: {time: number; visibility: FaceVisibility; note: string; incidentId: string}) => request<{id: string}>(`/analyses/${analysisId}/observations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(observation) }),
  events: () => request<EventItem[]>('/events'),
  audit: () => request<AuditItem[]>('/audit'),
  auditIntegrity: () => request<AuditIntegrity>('/audit/integrity'),
  reports: () => request<ReportsData>('/reports'),
  streams: () => request<StreamsResponse>('/streams'),
  discoverStreams: () => request<{ cameras: { baseUrl: string; streamUrl: string; probeUrl: string; server: string }[]; count: number }>('/streams/discover', { method: 'POST' }),
  toggleStreams: (running: boolean) => request<StreamsResponse>('/streams/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ running }) }),
  setStreamSource: (streamId: string, source: string) => request<StreamsResponse>(`/streams/${streamId}/source`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source }) }),
  streamDetections: () => request<StreamDetection[]>('/streams/detections'),
  captureStream: (streamId: string) => request<Clip>(`/streams/${streamId}/capture`, { method: 'POST' }),
  loadDemo: () => request<{ clips: Clip[]; recommendedClipStart: string; recommendedClipTime: string; sampleJournalCsv: string; notice: string }>('/demo/load', { method: 'POST' }),
  matchJournal: (payload: { clip_id: string; clip_start_time: string; csv_text: string; window_seconds: number; auto_queue: boolean }) =>
    request<{ clipId: string; clipFilename: string; totalRows: number; inClipCount: number; queuedAnalyses: string[]; rows: JournalRow[] }>('/journal/match', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }),
  upload: (file: File, cameraId: string, replaceClipId = '', onProgress?: (percent: number) => void, signal?: AbortSignal) =>
    uploadRequest(file, cameraId, replaceClipId, onProgress, signal),
  clearStreamAlerts: () => request<{ cleared: number }>('/events/clear-stream-alerts', { method: 'POST' }),
  watchlist: () => request<WatchlistEntry[]>('/watchlist'),
  addToWatchlist: (candidate_id: string, label: string, case_ref = '') => request<WatchlistEntry>('/watchlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id, label, case_ref }) }),
  removeWatchlist: (id: string) => request(`/watchlist/${id}`, { method: 'DELETE' }),
  liveEvidence: () => request<LiveEvidenceResponse>('/live-evidence'),
  renameLiveEvidence: (id: string, label: string) => request(`/live-evidence/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label }) }),
  promoteLiveToWatchlist: (id: string, label = '', case_ref = 'LIVE-CAPTURE') =>
    request<WatchlistEntry>(`/api/live-evidence/${id}/watchlist`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label, case_ref }) }),
  deleteLiveEvidence: (id: string) => request(`/live-evidence/${id}`, { method: 'DELETE' }),
  clearLiveEvidence: () => request<{ cleared: number }>('/live-evidence/clear', { method: 'POST' }),
  liveIncidents: () => request<LiveIncident[]>('/live-incidents'),
  deleteLiveIncident: (id: string) => request(`/live-incidents/${id}`, { method: 'DELETE' }),
  dossier: () => request<CaseDossier>('/dossier'),
  saveDossier: (payload: {
    fir_number: string;
    ncrp_ack: string;
    police_station: string;
    io_name: string;
    io_badge: string;
    atm_id: string;
    bank_name: string;
    fraud_type: string;
    loss_inr: number;
    notes: string;
  }) => request<CaseDossier>('/dossier', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  caseJourney: () => request<CaseJourney>('/cases/journey'),
  analyze: (payload: { clip_id: string; transaction_time: string; time_mode: 'clip' | 'absolute'; clip_start_time: string; transaction_ref: string; case_ref?: string; window_seconds: number }) =>
    request<{ id: string; status: string }>('/analyses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  review: (id: string, status: Candidate['reviewStatus'], note: string) =>
    request(`/candidates/${id}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, note }) }),
  search: (id: string, threshold = 0.52) => request<{ embeddingType?: string; matches: (Candidate & { similarity: number; filename: string })[]; notice: string }>('/search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: id, threshold }),
  }),
  deleteClip: (id: string) => request(`/clips/${id}`, { method: 'DELETE' }),
  integrity: (id: string) => request<{ verified: boolean; sourceMatches: boolean; analysisMatches: boolean; sourceSha256: string; analysisSha256: string; normalized: boolean; checkedAt: string; notice: string }>(`/clips/${id}/integrity`),
};

export const formatDuration = (seconds: number) => {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 3600)).padStart(2, '0')}:${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
};

export const formatBytes = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
