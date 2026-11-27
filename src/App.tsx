import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownRight, ArrowRight, BadgeCheck, BarChart3, Bell,
  Camera, Check, CheckCircle2, ChevronDown, ChevronRight, Clock3, Crosshair,
  Database, Download, Eye, EyeOff, FileClock, FileCode2, FileSearch, FileSpreadsheet, FileVideo2,
  Fingerprint, FolderOpen, Gauge, HardDrive, History, House, Link2, LoaderCircle, LogOut,
  LockKeyhole, Menu, Pencil, Play, Plus, Radio, RefreshCw, RotateCcw, Search, ScanFace,
  Shield, ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, Square, Trash2, Upload, UserRoundCheck,
  UsersRound, Video, X,
} from 'lucide-react';
import {
  api, Analysis, AuditIntegrity, AuditItem, AuthUser, CameraSlot, Candidate, CaseDossier, CaseJourney, Clip,
  DatabaseBackup, EventItem, FaceVisibility, formatBytes, formatDuration, Health, JournalRow,
  LiveEvidenceResponse, LiveEvidenceSubject, LiveIncident, ReportsData, SecurityOverview, StreamDetection, StreamsResponse, WatchlistEntry,
} from './api';
import ResponseDesk from './ResponseDesk';

type Page = 'surveillance' | 'desk' | 'intel' | 'library' | 'search' | 'reports' | 'audit' | 'review' | 'accounts' | 'security' | 'response';
type Toast = { kind: 'success' | 'error'; message: string } | null;
type SlotModalTarget = { channelId: string; streamId: string; replaceClipId?: string; mode?: 'file' | 'ipcam' } | null;
const validPages = new Set<Page>(['surveillance', 'desk', 'intel', 'library', 'search', 'reports', 'audit', 'accounts', 'security', 'response']);
const SESSION_SYNC_KEY = 'drishti-session-sync';

function announceSessionChange() {
  try { localStorage.setItem(SESSION_SYNC_KEY, `${Date.now()}`); } catch { /* Browser storage may be disabled. */ }
}

function initialPage(): Page {
  const tab = new URLSearchParams(window.location.search).get('tab') as Page | null;
  return tab && validPages.has(tab) ? tab : 'desk';
}

const pageCopy: Record<Page, { title: string; subtitle: string }> = {
  desk: { title: 'PS04 · ATM Suspect Face Extraction', subtitle: 'Link ATM CCTV / DVR footage to bank transaction timestamps, extract ranked suspect faces with quality flags & export sealed evidence.' },
  surveillance: { title: 'Real-Time Detection Console (Local Sandbox)', subtitle: 'Optional real-time local/IP-Webcam AI monitor that collects suspicious scene & face DB evidence automatically and alerts on repeat appearances (no live bank CCTV link).' },
  intel: { title: 'Case intel & journey', subtitle: 'Multi-camera suspect reconstruction, live SFace watchlist & courtroom readiness brief.' },
  library: { title: 'Video library', subtitle: 'Four local evidence channels with upload, replace, delete, FFmpeg normalization & container forensics.' },
  search: { title: 'Cross-clip search', subtitle: 'Search SFace 128-D face embeddings across other uploaded clips.' },
  reports: { title: 'Reports & analytics', subtitle: 'Forensic metrics, reliability flags, and 4-stream person detection telemetry.' },
  audit: { title: 'Audit trail', subtitle: 'Tamper-evident hash-linked operator actions and surveillance alerts.' },
  review: { title: 'Evidence review', subtitle: 'Compare raw and enhanced frames, inspect lighting, redact bystanders, flag suspect & seal evidence.' },
  accounts: { title: 'Access control', subtitle: 'Approve local investigator accounts and revoke access.' },
  security: { title: 'Security center', subtitle: 'Database health, SHA-256 sweeps, AES-256-GCM backups, and manifest seal verification.' },
  response: { title: 'Authority response desk', subtitle: 'Demonstrate alert triage, investigator handoff, and activity history using a fictional incident.' },
};

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  useEffect(() => {
    const syncSession = (event: StorageEvent) => {
      if (event.key === SESSION_SYNC_KEY) window.location.reload();
    };
    window.addEventListener('storage', syncSession);
    return () => window.removeEventListener('storage', syncSession);
  }, []);
  useEffect(() => {
    let alive = true;
    void api.authBootstrap().then(async (bootstrap) => {
      if (!alive) return;
      setSetupRequired(bootstrap.needsAdministrator);
      if (bootstrap.authenticated) {
        try {
          const session = await api.authMe();
          if (alive) { setUser(session.user); setSetupRequired(false); }
        } catch {
          /* unauthenticated */
        }
      }
      if (alive) setAuthLoading(false);
    }).catch(() => {
      if (alive) setAuthLoading(false);
    });
    const expire = () => { setUser(null); setSetupRequired(false); };
    window.addEventListener('drishti:session-expired', expire);
    return () => { alive = false; window.removeEventListener('drishti:session-expired', expire); };
  }, []);

  const signOut = async () => {
    try { await api.authLogout(); } finally { announceSessionChange(); setUser(null); }
  };
  if (authLoading) return <div className="auth-loading"><div className="brand-emblem"><ScanFace size={22} /></div><strong>DRISHTI</strong><span>Checking local access…</span></div>;
  if (!user) return <AuthPortal setupRequired={setupRequired} onAuthenticated={(account) => { announceSessionChange(); setSetupRequired(false); setUser(account); }} />;
  return <Workspace user={user} onSignOut={signOut} />;
}

function Workspace({ user, onSignOut }: { user: AuthUser; onSignOut: () => Promise<void> }) {
  const [page, setPage] = useState<Page>(initialPage);
  const [clips, setClips] = useState<Clip[]>([]);
  const [cameras, setCameras] = useState<CameraSlot[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [auditIntegrity, setAuditIntegrity] = useState<AuditIntegrity | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [reportData, setReportData] = useState<ReportsData | null>(null);
  const [streamsState, setStreamsState] = useState<StreamsResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState('');
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [toast, setToast] = useState<Toast>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [smallNavOpen, setSmallNavOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadCameraId, setUploadCameraId] = useState('ATM-01');
  const [replaceClipId, setReplaceClipId] = useState('');
  const [slotModal, setSlotModal] = useState<SlotModalTarget>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async (quiet = true) => {
    if (quiet && refreshInFlight.current) return;
    refreshInFlight.current = true;
    if (!quiet) setRefreshing(true);
    try {
      const [
        healthResult, clipsResult, camerasResult, analysesResult,
        eventsResult, auditResult, auditIntegrityResult, reportsResult,
        streamsResult, watchlistResult,
      ] = await Promise.allSettled([
        api.health(), api.clips(), api.cameras(), api.analyses(),
        api.events(), api.audit(), api.auditIntegrity(), api.reports(),
        api.streams(), api.watchlist(),
      ]);
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      if (clipsResult.status === 'fulfilled') setClips(clipsResult.value);
      if (camerasResult.status === 'fulfilled') setCameras(camerasResult.value);
      if (analysesResult.status === 'fulfilled') setAnalyses(analysesResult.value);
      if (eventsResult.status === 'fulfilled') setEvents(eventsResult.value);
      if (auditResult.status === 'fulfilled') setAudit(auditResult.value);
      if (auditIntegrityResult.status === 'fulfilled') setAuditIntegrity(auditIntegrityResult.value);
      if (reportsResult.status === 'fulfilled') setReportData(reportsResult.value);
      if (streamsResult.status === 'fulfilled') setStreamsState(streamsResult.value);
      if (watchlistResult.status === 'fulfilled') setWatchlist(watchlistResult.value);
      if ([healthResult, clipsResult, camerasResult, analysesResult].some((result) => result.status === 'rejected')) {
        if (!quiet) setToast({ kind: 'error', message: 'Could not reach the local API. Start the local server and retry.' });
      }
    } finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh(false);
    const timer = window.setInterval(() => void refresh(), 7000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const openReview = (analysisId: string) => {
    setSelectedAnalysisId(analysisId);
    setPage('review');
    setSmallNavOpen(false);
  };

  const openSearch = (candidateId = '') => {
    setSelectedCandidateId(candidateId);
    setPage('search');
    setSmallNavOpen(false);
  };

  const openSlotPicker = (cameraId: string, replaceId = '', defaultTab: 'file' | 'ipcam' = 'file') => {
    const streamId = cameraId.replace('ATM-', 'CAM-');
    setSlotModal({ channelId: cameraId, streamId, replaceClipId: replaceId, mode: defaultTab });
  };

  const triggerFilePicker = (cameraId: string, replaceId = '') => {
    setUploadCameraId(cameraId);
    setReplaceClipId(replaceId);
    setSlotModal(null);
    fileInput.current?.click();
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 500 * 1024 * 1024) {
      setToast({ kind: 'error', message: 'This clip is larger than 500 MB. Export a shorter transaction window and retry.' });
      return;
    }
    try {
      const clip = await api.upload(file, uploadCameraId, replaceClipId);
      setToast({ kind: 'success', message: replaceClipId ? `Replaced ${uploadCameraId} footage with ${clip.filename}.` : `${clip.filename} added to ${uploadCameraId}.` });
      setReplaceClipId('');
      await refresh();
    } catch (error) {
      setToast({ kind: 'error', message: error instanceof Error ? error.message : 'Upload failed.' });
    }
  };

  const deleteSlotClip = async (clip: Clip) => {
    try {
      await api.deleteClip(clip.id);
      setToast({ kind: 'success', message: `${clip.filename} removed from ${clip.cameraId}.` });
      await refresh();
    } catch (error) {
      setToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not delete clip.' });
    }
  };

  const selectedAnalysis = analyses.find((item) => item.id === selectedAnalysisId);
  const pageMeta = pageCopy[page];
  const warningCount = events.filter((item) => item.severity === 'warning' || item.severity === 'critical').length;

  const navButtons = (
    <nav className="main-nav" aria-label="Main navigation">
      <NavItem active={page === 'desk' || page === 'review'} label="Case desk" icon={<House size={15} />} onClick={() => { setPage('desk'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'surveillance'} label="Real-time AI" icon={<Radio size={15} />} count={streamsState?.running ? 4 : undefined} onClick={() => { setPage('surveillance'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'intel'} label="Case intel" icon={<ShieldAlert size={15} />} count={watchlist.length || undefined} onClick={() => { setPage('intel'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'response'} label="Response desk" icon={<Bell size={15} />} onClick={() => { setPage('response'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'library'} label="Video library" icon={<Camera size={15} />} count={clips.length || undefined} onClick={() => { setPage('library'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'search'} label="Face search" icon={<ScanFace size={15} />} onClick={() => openSearch()} />
      <NavItem active={page === 'reports'} label="Reports" icon={<BarChart3 size={15} />} onClick={() => { setPage('reports'); setSmallNavOpen(false); }} />
      <NavItem active={page === 'audit'} label="Audit" icon={<FileClock size={15} />} count={warningCount || undefined} onClick={() => { setPage('audit'); setSmallNavOpen(false); }} />
      {user.role === 'administrator' && <NavItem active={page === 'accounts'} label="Access" icon={<UsersRound size={15} />} onClick={() => { setPage('accounts'); setSmallNavOpen(false); }} />}
      {user.role === 'administrator' && <NavItem active={page === 'security'} label="Security" icon={<ShieldCheck size={15} />} onClick={() => { setPage('security'); setSmallNavOpen(false); }} />}
    </nav>
  );

  return (
    <div className="app-shell">
      <input id="clip-file-upload" name="clip_file" aria-label="Upload CCTV video clip" ref={fileInput} className="sr-only" type="file" accept="video/*,.mpeg,.mpg,.dav,.h264,.264,.ts,.m4v,.asf,.vob" onChange={handleUpload} />

      <header className="top-nav-shell">
        <div className="top-nav-inner">
          <div className="top-utility-row">
            <div className="brand-lockup">
              <button className="icon-button menu-toggle" aria-label="Open navigation" onClick={() => setSmallNavOpen(true)}><Menu size={20} /></button>
              <div className="brand-emblem" aria-hidden="true"><ScanFace size={21} strokeWidth={1.8} /></div>
              <div><strong>DRISHTI · PS04 FORENSIC COMMAND</strong><span>ATM CCTV SUSPECT FACE EXTRACTION &amp; REAL-TIME LOCAL AI</span></div>
            </div>

            <div className="top-utility-right">
              <div className="local-status"><span className={`status-orb ${health ? 'status-ready' : 'status-loading'}`} /><span>{health ? 'OFFLINE / LOCAL' : 'CONNECTING'}</span></div>
              <span className="topbar-divider" />
              <a className="button button-outline button-compact" href="/security-portal" target="_blank" rel="noopener noreferrer" title="Open Separate Guard & Escalation Security Portal">
                <ShieldAlert size={14} /> Security Portal ↗
              </a>
              <span className="topbar-divider" />
              <div className="topbar-clock"><span>JAIPUR, RJ</span><strong>{new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })}</strong></div>
              <span className="topbar-divider" />
              <button className="icon-button notification-button" aria-label="Recent alerts" onClick={() => setPage('audit')}><Bell size={18} />{warningCount > 0 && <i />}</button>
              <div className="profile-pill">
                <div className="profile-avatar">{user.displayName.slice(0, 2).toUpperCase()}</div>
                <div className="profile-copy"><strong>{user.displayName}</strong><span>{user.role === 'administrator' ? 'Administrator' : 'Investigator'}</span></div>
              </div>
              <button className="icon-button" aria-label="Sign out" title="Sign out" onClick={() => void onSignOut()}><LogOut size={18} /></button>
            </div>
          </div>

          <div className="top-tabs-row">
            {navButtons}
            <div className="nav-vault-pill"><HardDrive size={14} /> Local Vault · Zero Cloud · SHA-256</div>
          </div>
        </div>
      </header>

      <aside className={`mobile-drawer ${smallNavOpen ? 'mobile-drawer-open' : ''}`}>
        <div className="form-row">
          <div className="brand-lockup"><div className="brand-emblem"><ScanFace size={18} /></div><div><strong>DRISHTI</strong><span>PS04 COMMAND</span></div></div>
          <button className="icon-button" aria-label="Close navigation" onClick={() => setSmallNavOpen(false)}><X size={18} /></button>
        </div>
        {navButtons}
      </aside>
      {smallNavOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setSmallNavOpen(false)} />}

      {health?.runtime.mode === 'mock' && (
        <div className="mock-mode-banner" role="status">
          <AlertTriangle size={17} />
          <div><strong>MOCK / DEMONSTRATION MODE</strong><span>External identity, dispatch, and independent audit are unavailable unless configured. Storage encryption is not verified; legal and model validation are incomplete. Do not use real investigative footage.</span></div>
        </div>
      )}

      <main className="main-column">
        <div className="page-wrap">
          <div className="page-heading">
            <div><h1>{pageMeta.title}</h1><p>{pageMeta.subtitle}</p></div>
            <div className="page-actions">
              <span className="local-chip"><LockKeyhole size={14} /> LOCAL PROCESSING</span>
              <button className="button button-outline button-compact" onClick={() => void refresh(false)} disabled={refreshing}>
                <RefreshCw size={15} className={refreshing ? 'spin' : ''} /> Refresh
              </button>
            </div>
          </div>

          {page === 'surveillance' && (
            <SurveillanceWall
              state={streamsState}
              events={events}
              watchlist={watchlist}
              onRefresh={refresh}
              onOpenSlotModal={(streamId, mode) => setSlotModal({ channelId: streamId.replace('CAM-', 'ATM-'), streamId, mode })}
              onCaptureToDesk={() => { setPage('desk'); void refresh(); }}
              onToast={setToast}
            />
          )}
          {page === 'desk' && (
            <CaseDesk
              clips={clips}
              cameras={cameras}
              analyses={analyses}
              health={health}
              events={events}
              onAddOrChange={(camId, replaceId) => openSlotPicker(camId, replaceId, 'file')}
              onDeleteClip={(clip) => void deleteSlotClip(clip)}
              onReview={openReview}
              onRefresh={refresh}
              onToast={setToast}
            />
          )}
          {page === 'intel' && (
            <CaseIntel
              watchlist={watchlist}
              onReview={openReview}
              onOpenSurveillance={() => setPage('surveillance')}
              onRefresh={refresh}
              onToast={setToast}
            />
          )}
          {page === 'response' && <ResponseDesk user={user} clips={clips} analyses={analyses} audit={audit} auditIntegrity={auditIntegrity} onReview={openReview} />}
          {page === 'library' && (
            <Library
              clips={clips}
              cameras={cameras}
              onAddOrChange={(camId, replaceId) => openSlotPicker(camId, replaceId, 'file')}
              onDelete={(clip) => void deleteSlotClip(clip)}
            />
          )}
          {page === 'review' && <Review analysisId={selectedAnalysisId} analysisSummary={selectedAnalysis} canAnchor={user.role === 'administrator'} onOpenSearch={openSearch} onToast={setToast} onRefresh={refresh} />}
          {page === 'search' && <SearchWorkspace analyses={analyses} candidateId={selectedCandidateId} onCandidateChange={setSelectedCandidateId} onReview={openReview} />}
          {page === 'reports' && <Reports data={reportData} analyses={analyses} events={events} />}
          {page === 'audit' && <Audit items={audit} events={events} integrity={auditIntegrity} />}
          {page === 'accounts' && user.role === 'administrator' && <AccessControl currentUser={user} onToast={setToast} />}
          {page === 'security' && user.role === 'administrator' && <SecurityCenter onToast={setToast} />}
        </div>
      </main>

      {slotModal && (
        <SlotSourceModal
          target={slotModal}
          onClose={() => setSlotModal(null)}
          onChooseUpload={() => triggerFilePicker(slotModal.channelId, slotModal.replaceClipId || '')}
          onConnectIpCam={async (sourceUrl) => {
            await api.setStreamSource(slotModal.streamId, sourceUrl);
            if (!streamsState?.running) {
              await api.toggleStreams(true);
            }
            setToast({ kind: 'success', message: `${slotModal.streamId} connected to ${sourceUrl} with live AI detection.` });
            setSlotModal(null);
            setPage('surveillance');
            await refresh();
          }}
        />
      )}

      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span>{toast.kind === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}</span><p>{toast.message}</p><button aria-label="Dismiss message" onClick={() => setToast(null)}><X size={16} /></button></div>}
    </div>
  );
}

function SlotSourceModal({ target, onClose, onChooseUpload, onConnectIpCam }: {
  target: NonNullable<SlotModalTarget>;
  onClose: () => void;
  onChooseUpload: () => void;
  onConnectIpCam: (url: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<'choose' | 'ipcam'>(target.mode === 'ipcam' ? 'ipcam' : 'choose');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const connect = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setErr('');
    try {
      await onConnectIpCam(url.trim());
    } catch (error) {
      setErr(error instanceof Error ? error.message : 'Failed to connect stream.');
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="privacy-modal-backdrop" role="dialog" aria-modal="true" aria-label={`Assign footage or IP Webcam to ${target.channelId}`}>
      <div className="privacy-modal slot-modal">
        <div className="section-title">
          <div>
            <h2>{target.replaceClipId ? `Change ${target.channelId} / ${target.streamId} Source` : `Add Footage to ${target.channelId} / ${target.streamId}`}</h2>
            <p>Upload a recorded ATM CCTV video file or attach a live IP Webcam / local camera stream.</p>
          </div>
          <button className="icon-button" aria-label="Close source dialog" onClick={onClose}><X size={18} /></button>
        </div>

        {tab === 'choose' ? (
          <div className="slot-modal-tabs">
            <button type="button" className="slot-modal-option" onClick={onChooseUpload}>
              <strong><Upload size={17} /> Upload Video File</strong>
              <span>MP4, AVI, MOV, MKV, DAV, H264, TS. Stored locally with SHA-256 chain-of-custody.</span>
            </button>
            <button type="button" className="slot-modal-option" onClick={() => setTab('ipcam')}>
              <strong><Radio size={17} /> Connect IP Webcam / USB Cam</strong>
              <span>Paste a private IP Webcam address after configuring the allowed camera subnet, or use camera `0`.</span>
            </button>
          </div>
        ) : (
          <form className="intake-form" onSubmit={(e) => void connect(e)}>
            <label className="field-group" htmlFor="modal-ipcam-url">
              <span className="field-label">IP Webcam URL or Camera Index ({target.streamId})</span>
              <input
                id="modal-ipcam-url"
                name="modal_ipcam_url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="e.g. http://192.168.1.50:8080/video or rtsp://... or 0"
                required
              />
            </label>
            {err && <div className="auth-error" style={{ margin: 0 }}><AlertCircle size={15} />{err}</div>}
            <div className="form-row">
              <button type="button" className="button button-outline button-compact" onClick={() => setTab('choose')}>Back</button>
              <button type="submit" className="button button-primary button-compact" disabled={busy || !url.trim()}>
                {busy ? <LoaderCircle size={14} className="spin" /> : <Radio size={14} />} Connect Live Stream
              </button>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body
  );
}

function SurveillanceWall({ state, events, watchlist, onRefresh, onOpenSlotModal, onCaptureToDesk, onToast }: {
  state: StreamsResponse | null;
  events: EventItem[];
  watchlist: WatchlistEntry[];
  onRefresh: () => void;
  onOpenSlotModal: (streamId: string, mode: 'file' | 'ipcam') => void;
  onCaptureToDesk: () => void;
  onToast: (toast: Toast) => void;
}) {
  const [detections, setDetections] = useState<StreamDetection[]>([]);
  const [liveDb, setLiveDb] = useState<LiveEvidenceResponse | null>(null);
  const [incidents, setIncidents] = useState<LiveIncident[]>([]);
  const [previewIncident, setPreviewIncident] = useState<LiveIncident | null>(null);
  const [busy, setBusy] = useState(false);
  const [capturing, setCapturing] = useState('');
  const [tick, setTick] = useState(0);
  const [frameTick, setFrameTick] = useState(0);
  const [camTarget, setCamTarget] = useState('CAM-03');
  const [ipUrl, setIpUrl] = useState('');
  const [camSaving, setCamSaving] = useState(false);
  const pollInFlight = useRef(false);

  const loadDetections = useCallback(async () => {
    if (pollInFlight.current) return;
    pollInFlight.current = true;
    try {
      const [detList, dbEvidence, incList] = await Promise.all([api.streamDetections(), api.liveEvidence(), api.liveIncidents()]);
      setDetections(detList);
      setLiveDb(dbEvidence);
      setIncidents(incList);
    } catch {
      /* ignore transient poll error */
    } finally {
      pollInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void loadDetections();
    const timer = window.setInterval(() => {
      void loadDetections();
      onRefresh();
      setTick((v) => v + 1);
    }, 3000);
    const frameTimer = window.setInterval(() => {
      if (state?.running) setFrameTick((v) => v + 1);
    }, 360);
    return () => { window.clearInterval(timer); window.clearInterval(frameTimer); };
  }, [loadDetections, onRefresh, state?.running]);

  const promoteLive = async (subject: LiveEvidenceSubject) => {
    try {
      await api.promoteLiveToWatchlist(subject.id, subject.subjectCode);
      onToast({ kind: 'success', message: `${subject.subjectCode} armed on live SFace watchlist across all cameras.` });
      await loadDetections();
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not arm live subject.' });
    }
  };

  const deleteLive = async (subject: LiveEvidenceSubject) => {
    try {
      await api.deleteLiveEvidence(subject.id);
      onToast({ kind: 'success', message: `Removed ${subject.subjectCode} from live DB evidence.` });
      await loadDetections();
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not remove live evidence.' });
    }
  };

  const clearLiveDb = async () => {
    try {
      await api.clearLiveEvidence();
      onToast({ kind: 'success', message: 'Cleared auto-collected live DB evidence & incident captures.' });
      await loadDetections();
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not clear live DB evidence.' });
    }
  };

  const deleteIncident = async (id: string) => {
    try {
      await api.deleteLiveIncident(id);
      await loadDetections();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not delete incident snapshot.' });
    }
  };

  const toggle = async (running: boolean) => {
    setBusy(true);
    try {
      await api.toggleStreams(running);
      onToast({ kind: 'success', message: running ? 'Live person, face, occlusion & watchlist AI started.' : 'Surveillance streams paused.' });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not toggle surveillance streams.' });
    } finally {
      setBusy(false);
    }
  };

  const applyCameraSource = async (streamId: string, sourceValue: string) => {
    setCamSaving(true);
    try {
      await api.setStreamSource(streamId, sourceValue);
      if (sourceValue !== 'default' && sourceValue !== 'clear' && !state?.running) {
        await api.toggleStreams(true);
      }
      const msg = sourceValue === 'clear'
        ? `${streamId} feed cleared.`
        : sourceValue === 'default'
          ? `${streamId} reset to default pilot state.`
          : `${streamId} connecting to ${sourceValue}…`;
      onToast({ kind: 'success', message: msg });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not update camera feed.' });
    } finally {
      setCamSaving(false);
    }
  };

  const autoDiscoverPhone = async () => {
    setCamSaving(true);
    try {
      const res = await api.discoverStreams();
      if (!res.cameras.length) {
        onToast({ kind: 'error', message: 'No active IP Webcam found on Wi-Fi/hotspot (:8080/:4747). Start server in the app first.' });
        return;
      }
      const best = res.cameras[0];
      setIpUrl(best.streamUrl);
      await api.setStreamSource(camTarget, best.streamUrl);
      if (!state?.running) {
        await api.toggleStreams(true);
      }
      onToast({ kind: 'success', message: `Found ${best.server} on ${best.baseUrl} -> streaming on ${camTarget}!` });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Auto-scan failed.' });
    } finally {
      setCamSaving(false);
    }
  };

  const clearAlerts = async () => {
    try {
      await api.clearStreamAlerts();
      onToast({ kind: 'success', message: 'Cleared stream alert notifications.' });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not clear alerts.' });
    }
  };

  const capture = async (streamId: string) => {
    setCapturing(streamId);
    try {
      const clip = await api.captureStream(streamId);
      onToast({ kind: 'success', message: `Captured ${streamId} clip (${clip.filename}) into Case Desk.` });
      onCaptureToDesk();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Capture failed.' });
    } finally {
      setCapturing('');
    }
  };

  const running = Boolean(state?.running);
  const totalPersons = (state?.streams || []).reduce((sum, s) => sum + s.personCount, 0);
  const totalFaces = (state?.streams || []).reduce((sum, s) => sum + (s.faceCount || 0), 0);
  const streamAlerts = events.filter((e) => e.kind.startsWith('stream.') || e.kind.startsWith('suspicious.'));
  const faceStreams = (state?.streams || []).filter((s) => s.hasFaceCapture);
  const activeWatchlistHits = (state?.streams || []).filter((s) => s.watchlistHit);
  const activeRepeatHits = (state?.streams || []).filter((s) => s.repeatHit);
  const dbSubjects = liveDb?.subjects || [];

  return (
    <div className="wall-layout">
      <div className="wall-control-bar">
        <div className="wall-control-top">
          <div className="wall-banner-left">
            <div className="wall-banner-icon"><Video size={20} /></div>
            <div>
              <strong>God&apos;s Eye 4-Stream Live AI &amp; IP Webcam Console</strong>
              <span>2 default pilot feeds (`CAM-01`, `CAM-02`) + 2 open slots (`CAM-03`, `CAM-04`). Faces auto-save to DB &amp; alert on repeat entry.</span>
            </div>
          </div>
          <div className="wall-banner-actions">
            <span className="recorded-chip">
              <span /> {totalPersons} PERSONS · {totalFaces} FACES · {liveDb?.summary.totalSubjects ?? 0} DB ({liveDb?.summary.repeatSubjects ?? 0} REPEAT) · {watchlist.length} WATCHLIST
            </span>
            {running ? (
              <button className="button button-outline" disabled={busy} onClick={() => void toggle(false)}>
                <Square size={15} /> Stop 4-Stream Pilot
              </button>
            ) : (
              <button className="button button-primary" disabled={busy} onClick={() => void toggle(true)}>
                <Play size={15} /> Start 4-Stream Live AI
              </button>
            )}
          </div>
        </div>

        <form className="ipcam-bar" onSubmit={(e) => { e.preventDefault(); if (ipUrl.trim()) void applyCameraSource(camTarget, ipUrl.trim()); }}>
          <label className="ipcam-label" htmlFor="ipcam-target"><Link2 size={15} /> Connect Live IP Webcam / USB Cam:</label>
          <select id="ipcam-target" name="cam_target" className="ipcam-select" value={camTarget} onChange={(e) => setCamTarget(e.target.value)}>
            <option value="CAM-01">CAM-01 · Vestibule</option>
            <option value="CAM-02">CAM-02 · Keypad</option>
            <option value="CAM-03">CAM-03 · Dispenser (Open)</option>
            <option value="CAM-04">CAM-04 · Exit (Open)</option>
          </select>
          <input
            id="ipcam-url"
            name="ipcam_url"
            aria-label="IP Webcam URL or local camera index"
            className="ipcam-input"
            value={ipUrl}
            onChange={(e) => setIpUrl(e.target.value)}
            placeholder="e.g. http://192.168.1.50:8080/video or rtsp://... or 0 (Mac webcam)"
          />
          <button type="submit" className="button button-primary button-compact" disabled={camSaving || !ipUrl.trim()}>
            {camSaving ? <LoaderCircle size={14} className="spin" /> : <Radio size={14} />} Connect Feed
          </button>
          <button type="button" className="button button-outline button-compact" disabled={camSaving} onClick={() => void autoDiscoverPhone()}>
            {camSaving ? <LoaderCircle size={14} className="spin" /> : <Search size={14} />} Auto-Find Phone
          </button>
          <button type="button" className="button button-outline button-compact" disabled={camSaving} onClick={() => { setIpUrl(''); void applyCameraSource(camTarget, 'default'); }}>
            <RotateCcw size={14} /> Reset Slot
          </button>
          <span className="ipcam-hint">IP Webcam / DroidCam: paste a private IP such as <code>192.168.1.50:8080</code> after setting <code>DRISHTI_CAMERA_NETWORKS</code> (auto-finds <code>/video</code> and <code>/shot.jpg</code>)</span>
        </form>
      </div>

      <div className="wall-split">
        <div className="wall-grid">
          {(state?.streams || []).map((stream) => (
            <article className={`stream-card ${stream.alertState === 'alert' ? 'stream-card-alert' : ''}`} key={stream.id}>
              <div className="stream-viewport">
                {stream.sourceAvailable ? (
                  <img
                    src={running ? `${stream.snapshotUrl}?f=${frameTick}` : `${stream.snapshotUrl}?t=${tick}`}
                    alt={`${stream.id} ${stream.name} surveillance feed`}
                  />
                ) : (
                  <div className="stream-empty-overlay">
                    <Camera size={24} />
                    <span>{stream.id} · Open Slot</span>
                    <div className="stream-actions-row">
                      <button className="button button-outline button-compact" onClick={() => onOpenSlotModal(stream.id, 'file')}>
                        <Upload size={13} /> Add Video
                      </button>
                      <button className="button button-primary button-compact" onClick={() => onOpenSlotModal(stream.id, 'ipcam')}>
                        <Radio size={13} /> Add IP Webcam
                      </button>
                    </div>
                  </div>
                )}
                <span className={`stream-badge ${stream.alertState === 'alert' ? 'stream-badge-alert' : running && stream.sourceAvailable ? 'stream-badge-live' : ''}`}>
                  <i />
                  {stream.watchlistHit ? `WATCHLIST · ${stream.id}` : stream.repeatHit ? `REPEAT · ${stream.id}` : stream.alertState === 'alert' ? `ALERT · ${stream.id}` : stream.securityStage === 'observing_rule1' ? `RULE 1 OBS · ${stream.id}` : !stream.sourceAvailable ? `OPEN · ${stream.id}` : running ? `LIVE AI · ${stream.id}` : `STANDBY · ${stream.id}`}
                </span>
                {stream.sourceAvailable && (
                  <span className="stream-count-pill">
                    P:{stream.personCount} · F:{stream.faceCount ?? 0}{running && stream.fps > 0 ? ` · ${stream.fps} FPS` : ''}
                  </span>
                )}
              </div>
              <div className="stream-footer">
                <div className="stream-footer-meta">
                  <strong>{stream.name} ({stream.zone})</strong>
                  <small>
                    {stream.sourceLabel}
                    {stream.trackingEngine ? ` · ${stream.trackingEngine}` : ''}
                    {stream.status === 'reconnecting' && stream.lastError
                      ? ` · ${stream.lastError}`
                      : stream.lastAlert
                        ? ` · ${stream.lastAlert}`
                        : ''}
                  </small>
                </div>
                <div className="camera-actions-inline">
                  <button
                    className="icon-button"
                    aria-label={`Change ${stream.id} footage or IP Webcam`}
                    title="Add / Change footage or IP Webcam"
                    onClick={() => onOpenSlotModal(stream.id, 'ipcam')}
                  >
                    <Pencil size={14} />
                  </button>
                  {stream.sourceAvailable && (
                    <>
                      <button
                        className="icon-button danger-hover"
                        aria-label={`Remove ${stream.id} feed`}
                        title="Remove / Clear slot"
                        onClick={() => void applyCameraSource(stream.id, 'clear')}
                      >
                        <Trash2 size={14} />
                      </button>
                      <button
                        className="button button-outline button-compact"
                        disabled={capturing === stream.id}
                        onClick={() => void capture(stream.id)}
                      >
                        {capturing === stream.id ? <LoaderCircle size={13} className="spin" /> : <Plus size={13} />}
                        Capture
                      </button>
                    </>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>

        <aside className="wall-telemetry-col">
          {activeWatchlistHits.map((hit) => (
            <div className="watchlist-alert-banner" key={`hit-${hit.id}`}>
              <ShieldAlert size={18} />
              <span>LIVE SUSPECT MATCH on {hit.id}: {hit.watchlistHit}</span>
            </div>
          ))}

          {activeRepeatHits.map((hit) => (
            <div className="repeat-alert-banner" key={`rep-${hit.id}`}>
              <AlertTriangle size={18} />
              <span>REPEAT PERSON ALERT on {hit.id}: {hit.repeatHit}</span>
            </div>
          ))}

          <section className="panel telemetry-panel">
            <SectionTitle
              title="Live DB evidence &amp; repeat tracker"
              detail={`${liveDb?.summary.totalSubjects ?? 0} saved in DB · ${liveDb?.summary.repeatSubjects ?? 0} repeat · ${liveDb?.summary.totalSightings ?? 0} crops`}
              action={dbSubjects.length > 0 ? <button className="text-button" onClick={() => void clearLiveDb()}>Reset DB</button> : undefined}
            />
            {dbSubjects.length ? (
              <div className="live-db-list">
                {dbSubjects.map((sub) => (
                  <div className={`live-db-card ${sub.isRepeat ? 'live-db-card-repeat' : ''}`} key={sub.id}>
                    <img src={`${sub.imageUrl}?v=${sub.sightingCount}`} alt={sub.subjectCode} />
                    <div className="live-db-meta">
                      <div className="live-db-top">
                        <strong>{sub.subjectCode}</strong>
                        <span className={`repeat-count-pill ${sub.isRepeat ? 'is-repeat' : 'is-single'}`}>
                          {sub.isRepeat ? `REPEAT ${sub.appearanceCount}×` : 'SAVED 1×'}
                        </span>
                      </div>
                      <small>{sub.cameras.join(' → ')} · Q {Math.round(sub.bestScore)}/100 · {sub.sightingCount} crop(s)</small>
                      <small>Last: {new Date(sub.lastSeenAt).toLocaleTimeString('en-IN')}{sub.flags.length ? ` · ${sub.flags[0]}` : ''}</small>
                    </div>
                    <div className="live-db-actions">
                      <button
                        className="button button-outline button-compact"
                        title="Arm on persistent Watchlist"
                        onClick={() => void promoteLive(sub)}
                      >
                        <ShieldAlert size={12} /> Arm
                      </button>
                      <button
                        className="icon-button danger-hover"
                        aria-label={`Remove ${sub.subjectCode}`}
                        onClick={() => void deleteLive(sub)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : faceStreams.length ? (
              <div className="face-capture-strip">
                {faceStreams.map((fs) => (
                  <div className="face-capture-card" key={fs.id}>
                    <img src={`${fs.latestFaceUrl}?v=${encodeURIComponent(fs.latestFaceAt || '')}`} alt={`Latest face from ${fs.id}`} />
                    <div className="face-capture-info">
                      <strong>{fs.id} · Q {Math.round(fs.latestFaceScore || 0)}/100</strong>
                      <span>{fs.latestFaceAt ? new Date(fs.latestFaceAt).toLocaleTimeString('en-IN') : 'Live'}</span>
                      {fs.latestFaceFlags && fs.latestFaceFlags.length > 0 && (
                        <div className="face-capture-flags">
                          {fs.latestFaceFlags.slice(0, 2).map((fl) => <small key={fl}>{fl}</small>)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyLine icon={<ScanFace size={18} />} title="No live faces captured in DB yet" detail="Start 4-Stream Live AI or connect your IP Webcam. Clear faces save to SQLite DB and alert if they appear again." />
            )}
          </section>

          <section className="panel telemetry-panel">
            <SectionTitle
              title="Auto-captured incident snapshots"
              detail={`${incidents.length} suspicious scene(s) saved in DB`}
            />
            {incidents.length ? (
              <div className="incident-list">
                {incidents.slice(0, 10).map((inc) => (
                  <div className={`incident-card ${inc.severity === 'critical' ? 'incident-card-critical' : ''}`} key={inc.id}>
                    <button className="incident-thumb-btn" onClick={() => setPreviewIncident(inc)} title="Inspect saved evidence frame">
                      <img src={inc.imageUrl} alt={inc.summary} />
                    </button>
                    <div className="incident-meta">
                      <strong>{inc.summary}</strong>
                      <small>{inc.cameraId} · {inc.kind.replace('stream.', '')}{inc.subjectCode ? ` · ${inc.subjectCode}` : ''}</small>
                      <small>SHA {inc.sha256.slice(0, 10)} · {new Date(inc.occurredAt).toLocaleTimeString('en-IN')}</small>
                    </div>
                    <button className="icon-button danger-hover" aria-label="Remove incident" onClick={() => void deleteIncident(inc.id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyLine icon={<Camera size={18} />} title="No suspicious scene snapshots yet" detail="Shoulder-surfing, repeat visitor, mask/helmet, loitering & keypad tampering automatically save full scene photos here." />
            )}
          </section>

          <section className="panel telemetry-panel">
            <SectionTitle
              title="Live suspicious alerts"
              detail={`${streamAlerts.length} alert(s)`}
              action={streamAlerts.length > 0 ? <button className="text-button" onClick={() => void clearAlerts()}>Clear</button> : undefined}
            />
            {streamAlerts.length ? (
              <div className="activity-list telemetry-scroll">
                {streamAlerts.slice(0, 12).map((alert) => (
                  <div className="activity-item" key={alert.id}>
                    <span className="activity-pin pin-amber" />
                    <div>
                      <strong>{alert.message}</strong>
                      <time>{alert.kind} · {new Date(alert.occurredAt).toLocaleTimeString('en-IN')}</time>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyLine icon={<AlertTriangle size={18} />} title="No suspicious alerts" detail="Watchlist matches, repeat visitors, shoulder-surfing, tampering, mask/cap occlusion & loitering alerts appear here." />
            )}
          </section>

          <section className="panel telemetry-panel">
            <SectionTitle title="Live detection log" detail="Recent person &amp; face hits" />
            {detections.length ? (
              <div className="table-scroll telemetry-scroll">
                <table className="data-table">
                  <thead><tr><th>CAM</th><th>TRACK</th><th>PERSONS</th><th>ALERT</th><th>TIME</th></tr></thead>
                  <tbody>
                    {detections.slice(0, 10).map((row) => (
                      <tr key={row.id}>
                        <td><span className="camera-id-pill">{row.cameraId}</span></td>
                        <td className="mono-data">#{String(row.trackId).padStart(2, '0')}</td>
                        <td className="mono-data">{row.personCount}</td>
                        <td>{row.alertKind ? <span className="severity severity-warning">{row.alertKind.replace('stream.', '')}</span> : 'normal'}</td>
                        <td className="mono-data">{new Date(row.occurredAt).toLocaleTimeString('en-IN')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyLine icon={<UsersRound size={18} />} title="Awaiting stream detections" detail="Person & face detections log automatically while streams run." />
            )}
          </section>
        </aside>
      </div>
      {previewIncident && createPortal(
        <div className="privacy-modal-backdrop" role="dialog" aria-modal="true" aria-label="Auto-captured incident snapshot" onClick={() => setPreviewIncident(null)}>
          <div className="privacy-modal slot-modal" onClick={(e) => e.stopPropagation()}>
            <div className="section-title">
              <div>
                <h2>{previewIncident.cameraId} · {previewIncident.kind.replace('stream.', '').toUpperCase()}</h2>
                <p>{previewIncident.summary}</p>
              </div>
              <button className="icon-button" aria-label="Close modal" onClick={() => setPreviewIncident(null)}><X size={18} /></button>
            </div>
            <img className="incident-modal-img" src={previewIncident.imageUrl} alt={previewIncident.summary} />
            <div className="review-disclaimer" style={{ marginTop: 10 }}>
              <ShieldCheck size={16} />
              <span>Captured {new Date(previewIncident.occurredAt).toLocaleString('en-IN')} · SHA-256: {previewIncident.sha256.slice(0, 18)}…</span>
            </div>
            <div className="form-row" style={{ marginTop: 10 }}>
              <span className="local-chip"><LockKeyhole size={14} /> AUTO-SAVED DB EVIDENCE</span>
              <div className="stream-actions-row">
                <a className="button button-outline button-compact" href={`/api/live-incidents/${previewIncident.id}.pdf`} download>
                  <FileSearch size={14} /> Incident PDF
                </a>
                <a className="button button-primary button-compact" href={previewIncident.imageUrl} download={`incident-${previewIncident.cameraId}-${previewIncident.id.slice(0, 8)}.jpg`}>
                  <Download size={14} /> Download Snapshot
                </a>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

function CaseIntel({ watchlist, onReview, onOpenSurveillance, onRefresh, onToast }: {
  watchlist: WatchlistEntry[];
  onReview: (id: string) => void;
  onOpenSurveillance: () => void;
  onRefresh: () => void;
  onToast: (toast: Toast) => void;
}) {
  const [journey, setJourney] = useState<CaseJourney | null>(null);
  const [dossier, setDossier] = useState<CaseDossier>({
    id: 'ACTIVE', firNumber: '', ncrpAck: '', policeStation: 'Cyber Crime Police Station',
    ioName: '', ioBadge: '', atmId: '', bankName: '', fraudType: 'ATM Cash-Out / Card Fraud',
    lossInr: 0, notes: '', updatedAt: '',
  });
  const [savingDossier, setSavingDossier] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [j, d] = await Promise.all([api.caseJourney(), api.dossier()]);
      setJourney(j);
      setDossier(d);
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not load case intelligence.' });
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveDossier = async (e: FormEvent) => {
    e.preventDefault();
    if (!dossier) return;
    setSavingDossier(true);
    try {
      const saved = await api.saveDossier({
        fir_number: dossier.firNumber,
        ncrp_ack: dossier.ncrpAck,
        police_station: dossier.policeStation,
        io_name: dossier.ioName,
        io_badge: dossier.ioBadge,
        atm_id: dossier.atmId,
        bank_name: dossier.bankName,
        fraud_type: dossier.fraudType,
        loss_inr: Number(dossier.lossInr) || 0,
        notes: dossier.notes,
      });
      setDossier(saved);
      onToast({ kind: 'success', message: 'Case Dossier saved. Stamped onto BSA Sec 63 Certs & PDF Evidence Bundles.' });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not save dossier.' });
    } finally {
      setSavingDossier(false);
    }
  };

  const removeWatch = async (id: string) => {
    try {
      await api.removeWatchlist(id);
      onToast({ kind: 'success', message: 'Removed suspect from live watchlist.' });
      onRefresh();
      await load();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Failed to remove watchlist item.' });
    }
  };

  return (
    <>
      <div className="stat-row">
        <Stat label="Case readiness" value={`${journey?.readinessScore ?? 0}%`} detail={journey?.auditVerified ? 'Audit chain verified' : 'Check security center'} icon={<ShieldCheck size={19} />} tone="teal" />
        <Stat label="Camera coverage" value={`${journey?.channelsCovered ?? 0} / 4`} detail={`${journey?.clipCount ?? 0} clip(s) · ${journey?.liveSubjects ?? 0} live DB`} icon={<Camera size={19} />} />
        <Stat label="Cross-cam SFace links" value={journey?.crossLinks.length ?? 0} detail={`${journey?.bestFaceQuality ?? 0}/100 peak face score`} icon={<ScanFace size={19} />} tone="amber" />
        <Stat label="Active watchlist" value={watchlist.length} detail={`${journey?.repeatSubjects ?? 0} repeat · ${journey?.alertCount ?? 0} alert(s)`} icon={<ShieldAlert size={19} />} tone="red" />
      </div>

      <div className="intel-grid">
        <div className="review-side-stack">
          <section className="panel telemetry-panel">
            <SectionTitle
              title="Live Case Suspect Watchlist (Local SFace)"
              detail="Flagged candidates trigger instant alerts across all 4 cameras & IP Webcams"
              action={<button className="button button-outline button-compact" onClick={onOpenSurveillance}><Radio size={13} /> Open Live Wall</button>}
            />
            {watchlist.length ? (
              <div>
                {watchlist.map((w) => (
                  <div className="watchlist-card-row" key={w.id}>
                    <img src={w.imageUrl} alt={w.label} />
                    <div>
                      <strong>{w.label}</strong>
                      <span>{w.caseRef || 'Active local case'} · Armed for live SFace matching</span>
                    </div>
                    <button className="icon-button danger-hover" aria-label={`Remove ${w.label} from watchlist`} onClick={() => void removeWatch(w.id)}>
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyLine icon={<ShieldAlert size={18} />} title="No suspects armed on live watchlist" detail="Open Evidence Review on any candidate and click 'Arm Live Watchlist' to alert across all cameras." />
            )}
          </section>

          <section className="panel telemetry-panel">
            <SectionTitle
              title="1930 NCRP / FIR &amp; Bank Fraud Dossier"
              detail="Metadata stamped into BSA Sec. 63 Certificates, PDF Sheets &amp; Case Bundles (never stores card/PIN)"
            />
            {dossier && (
              <form onSubmit={(e) => void saveDossier(e)}>
                <div className="dossier-grid">
                  <input id="dossier-fir" name="fir_number" placeholder="FIR / GD Ref (e.g. FIR-0412/2026)" value={dossier.firNumber} onChange={(e) => setDossier({ ...dossier, firNumber: e.target.value })} />
                  <input id="dossier-ncrp" name="ncrp_ack" placeholder="NCRP 1930 Ack No." value={dossier.ncrpAck} onChange={(e) => setDossier({ ...dossier, ncrpAck: e.target.value })} />
                  <input id="dossier-station" name="police_station" placeholder="Cyber Police Station / Unit" value={dossier.policeStation} onChange={(e) => setDossier({ ...dossier, policeStation: e.target.value })} />
                  <input id="dossier-io" name="io_name" placeholder="Investigating Officer Name" value={dossier.ioName} onChange={(e) => setDossier({ ...dossier, ioName: e.target.value })} />
                  <input id="dossier-badge" name="io_badge" placeholder="IO Badge / Belt ID" value={dossier.ioBadge} onChange={(e) => setDossier({ ...dossier, ioBadge: e.target.value })} />
                  <input id="dossier-bank" name="bank_name" placeholder="Bank / White-Label ATM Operator" value={dossier.bankName} onChange={(e) => setDossier({ ...dossier, bankName: e.target.value })} />
                  <input id="dossier-atm" name="atm_id" placeholder="ATM Terminal ID (e.g. S1CN4412)" value={dossier.atmId} onChange={(e) => setDossier({ ...dossier, atmId: e.target.value })} />
                  <input id="dossier-loss" name="loss_inr" type="number" min={0} placeholder="Fraud Amount (INR ₹)" value={dossier.lossInr || ''} onChange={(e) => setDossier({ ...dossier, lossInr: Number(e.target.value) || 0 })} />
                </div>
                <div className="dossier-grid">
                  <select id="dossier-fraud" name="fraud_type" value={dossier.fraudType} onChange={(e) => setDossier({ ...dossier, fraudType: e.target.value })}>
                    <option value="ATM Cash-Out / Card Fraud">ATM Cash-Out / Card Fraud</option>
                    <option value="Card Skimming / Shimming">Card Skimming / Shimming</option>
                    <option value="Card Swapping / Shoulder Surfing">Card Swapping / Shoulder Surfing</option>
                    <option value="Mule Account Withdrawal">Mule Account Withdrawal</option>
                  </select>
                  <button className="button button-primary button-compact" type="submit" disabled={savingDossier}>
                    {savingDossier ? <LoaderCircle size={14} className="spin" /> : <BadgeCheck size={14} />} Save Case Dossier
                  </button>
                </div>
              </form>
            )}
          </section>

          <section className="panel telemetry-panel">
            <SectionTitle title="Cross-Camera SFace Re-ID Links" detail="Automated correlation across ATM-01..ATM-04 clips" />
            {journey?.crossLinks.length ? (
              journey.crossLinks.map((link, i) => (
                <div className="crosslink-pill" key={`${link.sourceCandidateId}-${i}`}>
                  <div>
                    <strong>{link.sourceCamera} → {link.targetCamera}</strong>
                    <div><span>{link.similarity}% SFace 128-D match</span></div>
                  </div>
                  <button className="button button-outline button-compact" onClick={() => onReview(link.targetAnalysisId)}>Inspect</button>
                </div>
              ))
            ) : (
              <EmptyLine icon={<Fingerprint size={18} />} title="No cross-camera links yet" detail="Analyze 2+ ATM clips to reconstruct multi-camera suspect movement automatically." />
            )}
          </section>
        </div>

        <section className="panel telemetry-panel">
          <SectionTitle
            title="Multi-Camera Suspect Journey &amp; Fraud Brief"
            detail={loading ? 'Correlating clips, transactions & alerts…' : 'Chronological reconstruction for Cyber Cell briefing'}
            action={<button className="button button-outline button-compact" onClick={() => void load()}><RefreshCw size={13} /> Refresh Intel</button>}
          />
          {journey?.timeline.length ? (
            <div className="activity-list">
              {journey.timeline.map((item) => (
                <div className="activity-item" key={item.id}>
                  <span className={`activity-pin ${item.severity === 'warning' || item.severity === 'critical' ? 'pin-amber' : ''}`} />
                  <div>
                    <strong>
                      <span className={`journey-stage journey-stage-${item.stage}`}>{item.cameraId} · {item.stage.replace('_', ' ')}</span>
                      {item.title}
                    </strong>
                    <time>{item.detail} · {new Date(item.timestamp).toLocaleString('en-IN')}</time>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyLine icon={<History size={18} />} title="Case timeline empty" detail="Load the Demo Case or upload clips to generate a multi-camera forensic timeline." />
          )}
          <div className="review-disclaimer" style={{ marginTop: 14 }}>
            <Shield size={15} />
            <span>{journey?.notice || 'Decision-support correlation across workspace evidence only. Requires investigator verification.'}</span>
          </div>
        </section>
      </div>
    </>
  );
}

function AuthPortal({ setupRequired, onAuthenticated }: { setupRequired: boolean; onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>(setupRequired ? 'signup' : 'login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setNotice(''); setBusy(true);
    try {
      if (mode === 'signup') {
        const result = await api.authSignup(name, email, password);
        if (result.approvalRequired) {
          setMode('login'); setPassword('');
          setNotice('Request submitted. An administrator must approve this investigator account before sign-in.');
        } else onAuthenticated(result.user);
      } else {
        const result = await api.authLogin(email, password); onAuthenticated(result.user);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not complete account request.'); }
    finally { setBusy(false); }
  };

  return <main className="auth-screen">
    <div className="auth-side-art">
      <div className="auth-brand"><div className="brand-emblem"><ScanFace size={22} /></div><div><strong>DRISHTI</strong><span>CYBER CELL FORENSIC SUITE</span></div></div>
      <div className="auth-art-copy"><span className="auth-kicker"><ShieldCheck size={15} /> RAJASTHAN POLICE PS04 PILOT</span><h1>Careful review.<br /><em>Clear evidence.</em></h1><p>Transaction-linked ATM suspect face extraction, 128-D local embeddings, and 4-stream surveillance analytics.</p></div>
      <div className="auth-art-foot"><LockKeyhole size={15} /> Evidence, models, and cryptographic seals stay offline on this device.</div>
    </div>
    <section className="auth-panel">
      <div className="auth-mobile-brand"><div className="brand-emblem"><ScanFace size={22} /></div><strong>DRISHTI</strong></div>
      <div className="auth-card">
        <span className="auth-kicker">{setupRequired && mode === 'signup' ? 'INITIAL ADMINISTRATOR SETUP' : 'AUTHORISED ACCESS'}</span>
        <h2>{mode === 'signup' ? (setupRequired ? 'Secure this workspace' : 'Request an account') : 'Welcome back'}</h2>
        <p className="auth-description">{mode === 'signup' ? setupRequired ? 'Create the first administrator account. This account can approve future investigators.' : 'New accounts require administrator approval before accessing case material.' : 'Sign in with your local investigator account to continue.'}</p>
        {notice && <div className="auth-notice" role="status"><CheckCircle2 size={17} />{notice}</div>}
        {error && <div className="auth-error" role="alert"><AlertCircle size={17} />{error}</div>}
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          {mode === 'signup' && <label htmlFor="auth-name">Full name<input id="auth-name" name="display_name" autoComplete="name" required minLength={2} maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="Investigator name" /></label>}
          <label htmlFor="auth-email">Work email<input id="auth-email" name="email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="officer@cybercell.gov.in" /></label>
          <label htmlFor="auth-password">Passphrase<input id="auth-password" name="password" type="password" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={mode === 'signup' ? 12 : 1} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === 'signup' ? 'At least 12 characters' : 'Your passphrase'} /></label>
          {mode === 'signup' && <div className="auth-security-note"><Shield size={16} /> Passphrases are stored as salted scrypt hashes. No password recovery service is configured.</div>}
          <button className="button button-primary auth-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <LockKeyhole size={16} />}{mode === 'signup' ? (setupRequired ? 'Create administrator account' : 'Request investigator access') : 'Sign in securely'}<ArrowRight size={16} /></button>
        </form>
        <div className="auth-switch">{mode === 'login' ? <>Need access? <button onClick={() => { setMode('signup'); setError(''); setNotice(''); }}>Request an account</button></> : <>Already authorised? <button onClick={() => { setMode('login'); setError(''); setNotice(''); }}>Return to sign in</button></>}</div>
        <div className="auth-local-footer"><span className="live-dot" /> Local-only sign-in <span>·</span> Not an official Rajasthan Police system</div>
      </div>
    </section>
  </main>;
}

function SecurityCenter({ onToast }: { onToast: (toast: Toast) => void }) {
  const [overview, setOverview] = useState<SecurityOverview | null>(null);
  const [backups, setBackups] = useState<DatabaseBackup[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<'check' | 'backup' | 'manifest' | ''>('');
  const [backupPassphrase, setBackupPassphrase] = useState('');
  const [manifestText, setManifestText] = useState('');
  const [manifestResult, setManifestResult] = useState<{ verified: boolean; blockchain: boolean; payloadSha256?: string; reason?: string } | null>(null);
  const [evidenceResult, setEvidenceResult] = useState<Awaited<ReturnType<typeof api.verifyAllEvidence>> | null>(null);

  const load = async () => {
    try {
      const [state, snapshots] = await Promise.all([api.securityOverview(), api.databaseBackups()]);
      setOverview(state); setBackups(snapshots);
    } catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not load the security posture.' }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const verifyEvidence = async () => {
    setWorking('check'); setEvidenceResult(null);
    try {
      const result = await api.verifyAllEvidence(); setEvidenceResult(result); await load();
      onToast({ kind: result.mismatches.length ? 'error' : 'success', message: result.mismatches.length ? `${result.mismatches.length} evidence file integrity mismatch(es) found.` : `${result.checked} evidence clip(s) passed hash verification.` });
    } catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Evidence verification failed.' }); }
    finally { setWorking(''); }
  };

  const createBackup = async (event: FormEvent) => {
    event.preventDefault();
    if (backupPassphrase.length < 16) return;
    setWorking('backup');
    try {
      const created = await api.createDatabaseBackup(backupPassphrase);
      setBackupPassphrase(''); setBackups((items) => [created, ...items]); await load();
      onToast({ kind: 'success', message: 'Encrypted database snapshot created and integrity-checked.' });
    } catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Database snapshot failed.' }); }
    finally { setWorking(''); }
  };

  const checkManifest = async (event: FormEvent) => {
    event.preventDefault();
    setWorking('manifest');
    setManifestResult(null);
    try {
      const parsed = JSON.parse(manifestText);
      const blockchain = typeof parsed?.transactionHash === 'string' || typeof parsed?.chainId === 'string';
      const result = blockchain ? await api.verifyBlockchainEvidence(parsed) : await api.verifyManifest(parsed);
      setManifestResult({ ...result, blockchain });
      onToast({ kind: result.verified ? 'success' : 'error', message: result.verified ? (blockchain ? 'Blockchain fingerprint verified.' : 'Local manifest seal verified.') : (result.reason || 'Manifest verification failed.') });
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Paste valid JSON from an exported evidence manifest.' });
    } finally {
      setWorking('');
    }
  };

  const dbHealthy = overview?.database.integrity === 'ok' && overview.database.foreignKeyViolations === 0;
  const permissionsHealthy = Boolean(overview?.database.directoryPermissions.restricted && overview.database.filePermissions.restricted);
  const auditHealthy = Boolean(overview?.audit.verified);
  const formatStamp = (value: string) => new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });

  return <div className="security-workspace">
    <div className="security-banner"><div className="security-banner-icon"><ShieldCheck size={22} /></div><div><strong>Defence in depth for local forensic evidence</strong><span>SHA-256 chain of custody, HMAC-SHA256 manifest seals, and AES-256-GCM snapshots.</span></div><button className="button button-outline button-compact" onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /> Recheck</button></div>
    <div className="security-cards">
      <SecurityCard icon={<Database size={18} />} title="SQLite health" value={loading ? 'Checking…' : dbHealthy ? 'Healthy' : 'Review required'} detail={overview ? `${overview.database.integrity} · ${overview.database.foreignKeyViolations} foreign-key issues · ${formatBytes(overview.database.sizeBytes)}` : 'Running integrity checks'} ok={dbHealthy} />
      <SecurityCard icon={<Fingerprint size={18} />} title="Audit chain" value={loading ? 'Checking…' : auditHealthy ? 'Verified' : 'Integrity alert'} detail={overview ? `${overview.audit.entriesChecked} linked entries checked` : 'Verifying linked records'} ok={auditHealthy} />
      <SecurityCard icon={<HardDrive size={18} />} title="Local file permissions" value={loading ? 'Checking…' : permissionsHealthy ? 'Restricted' : 'Review permissions'} detail={overview ? `Data folder ${overview.database.directoryPermissions.mode} · DB ${overview.database.filePermissions.mode}` : 'Checking private storage modes'} ok={permissionsHealthy} />
      <SecurityCard icon={<UsersRound size={18} />} title="Account signals" value={overview ? `${overview.accounts.pending} pending approval` : 'Checking…'} detail={overview ? `${overview.accounts.active} active · ${overview.accounts.failedSignins24h} denied sign-ins in 24h` : 'Loading local account status'} ok={Boolean(overview && overview.accounts.failedSignins24h === 0 && overview.accounts.pending === 0)} />
      <SecurityCard icon={<LockKeyhole size={18} />} title="Host disk encryption" value="Verify on device" detail="Enable FileVault, BitLocker or LUKS for the volume storing local evidence." ok={false} />
      <SecurityCard icon={<Shield size={18} />} title="Network exposure" value="Loopback only" detail="Binds strictly to 127.0.0.1. External cloud services and telemetry remain disabled." ok />
    </div>

    <div className="security-tools-grid">
      <section className="panel security-tool-panel"><SectionTitle title="Evidence integrity sweep" detail="Rehash original recordings and analysis copies against ingest fingerprints." />
        <div className="security-tool-body"><div className="security-tool-icon"><Fingerprint size={19} /></div><div className="security-tool-copy"><strong>{overview?.evidence.clipCount ?? 0} clip(s) in local vault</strong><span>{overview?.evidence.lastFullCheck ? `Last full check ${formatStamp(overview.evidence.lastFullCheck.checkedAt)} · ${overview.evidence.lastFullCheck.mismatchCount} mismatch(es)` : 'No full evidence verification has been run yet.'}</span></div></div>
        <button className="button button-primary" onClick={() => void verifyEvidence()} disabled={loading || working !== '' || !overview?.evidence.clipCount}>{working === 'check' ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />} Run full evidence check</button>
        {evidenceResult && <div className={`security-result ${evidenceResult.mismatches.length ? 'security-result-error' : ''}`} role="status"><strong>{evidenceResult.verified}/{evidenceResult.checked} files verified</strong><span>{evidenceResult.notice}</span>{evidenceResult.mismatches.map((item) => <small key={item.clipId}>{item.filename} · source {item.sourceMatches ? 'OK' : 'MISMATCH'} · analysis {item.analysisMatches ? 'OK' : 'MISMATCH'}</small>)}</div>}
      </section>

      <section className="panel security-tool-panel"><SectionTitle title="Encrypted database snapshot" detail="Make a portable, authenticated SQLite metadata backup." />
        <form className="security-backup-form" onSubmit={(event) => void createBackup(event)}>
          <input type="text" name="username" autoComplete="username" value="drishti-backup" readOnly className="sr-only" aria-hidden="true" tabIndex={-1} />
          <label htmlFor="backup-passphrase">Backup passphrase<input id="backup-passphrase" name="passphrase" type="password" autoComplete="new-password" minLength={16} maxLength={256} required value={backupPassphrase} onChange={(event) => setBackupPassphrase(event.target.value)} placeholder="Use 16+ characters; keep it safe" /></label>
          <button className="button button-primary" type="submit" disabled={working !== '' || backupPassphrase.length < 16}>{working === 'backup' ? <LoaderCircle size={15} className="spin" /> : <LockKeyhole size={15} />} Create encrypted snapshot</button>
        </form>
        <p className="security-warning"><AlertCircle size={15} /> AES-256-GCM encrypted. The passphrase is not saved. Back up uploaded clips separately.</p>
        {backups.length > 0 && <div className="backup-list"><strong>Recent snapshots</strong>{backups.slice(0, 5).map((backup) => <div className="backup-row" key={backup.id}><div><span>{formatStamp(backup.createdAt)}</span><code>{backup.sha256.slice(0, 20)}…</code></div><a className="button button-outline button-compact" href={`/api/security/database-backups/${backup.id}`}><Download size={14} /> Download</a></div>)}</div>}
        {!backups.length && <div className="security-empty">No encrypted database snapshot yet.</div>}
      </section>
    </div>

    <section className="panel security-tool-panel">
      <SectionTitle title="Evidence verifier" detail="Paste an exported manifest to check its local seal, or paste a blockchain bundle to check its recorded fingerprint." />
      <form className="security-backup-form" onSubmit={(event) => void checkManifest(event)}>
        <textarea id="manifest-json" name="manifest_json" aria-label="Evidence manifest JSON" className="manifest-textarea" value={manifestText} onChange={(e) => { setManifestText(e.target.value); setManifestResult(null); }} placeholder="Paste the downloaded JSON here" required />
        <button className="button button-primary" type="submit" disabled={working !== '' || !manifestText.trim()}>
          {working === 'manifest' ? <LoaderCircle size={15} className="spin" /> : <FileCode2 size={15} />} Verify evidence
        </button>
      </form>
      {manifestResult && (
        <div className={`security-result ${manifestResult.verified ? '' : 'security-result-error'}`} role="status">
          <strong>{manifestResult.verified ? (manifestResult.blockchain ? 'BLOCKCHAIN FINGERPRINT VERIFIED' : 'LOCAL SEAL VERIFIED') : 'VERIFICATION FAILED'}</strong>
          <span>{manifestResult.verified ? `Payload SHA-256: ${manifestResult.payloadSha256}` : manifestResult.reason}</span>
        </div>
      )}
    </section>

    <section className="panel security-tool-panel">
      <SectionTitle
        title="Indian Law Enforcement &amp; Enterprise Compliance Matrix"
        detail="Evidence export, bystander redaction, local security controls and model inventory."
        action={<a className="button button-outline button-compact" href="/api/security/compliance-report.json" download><Download size={14} /> Compliance JSON</a>}
      />
      <div className="compliance-pills">
        <span className="compliance-pill"><BadgeCheck size={14} /> BSA Sec. 63 Cert Export</span>
        <span className="compliance-pill"><ShieldCheck size={14} /> DPDP Bystander Redaction</span>
        <span className="compliance-pill"><LockKeyhole size={14} /> 127.0.0.1 Zero-Cloud Boundary</span>
        <span className="compliance-pill"><Fingerprint size={14} /> Dual SHA-256 + HMAC-SHA256</span>
        <span className="compliance-pill"><CheckCircle2 size={14} /> Apache-2.0 / MIT AI Models (No AGPL)</span>
      </div>
    </section>

    <div className="security-disclaimer"><LockKeyhole size={15} /> This local security layer is not a certified police deployment. Keep evidence on an encrypted host volume and maintain externally signed checkpoints.</div>
  </div>;
}

function SecurityCard({ icon, title, value, detail, ok = false }: { icon: React.ReactNode; title: string; value: string; detail: string; ok?: boolean }) {
  return <article className={`security-card ${ok ? 'security-card-ok' : 'security-card-review'}`}><div className="security-card-top"><span className="security-card-icon">{icon}</span><span className="security-card-state"><i />{ok ? 'PASS' : 'ACTION'}</span></div><span className="security-card-label">{title}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function AccessControl({ currentUser, onToast }: { currentUser: AuthUser; onToast: (toast: Toast) => void }) {
  const [accounts, setAccounts] = useState<Awaited<ReturnType<typeof api.accounts>>>([]);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState('');
  const load = async () => { try { setAccounts(await api.accounts()); } catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not load accounts.' }); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, []);
  const setStatus = async (account: (typeof accounts)[number], status: 'active' | 'disabled') => {
    setPendingId(account.id);
    try {
      await api.updateAccount(account.id, status);
      onToast({ kind: 'success', message: `${account.email} ${status === 'active' ? 'approved' : 'disabled'}.` });
      await load();
    } catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not update account.' }); }
    finally { setPendingId(''); }
  };
  return <div className="access-layout"><section className="access-panel"><div className="section-title"><div><h2>Investigator accounts</h2><p>Only approved accounts can open evidence or case history.</p></div><span className="access-count"><UsersRound size={15} /> {accounts.length} local</span></div>
    {loading ? <div className="access-empty">Loading local accounts…</div> : !accounts.length ? <div className="access-empty">No accounts registered.</div> : <div className="account-list">{accounts.map((account) => <article className="account-row" key={account.id}>
      <div className="profile-avatar">{account.displayName.slice(0, 2).toUpperCase()}</div><div className="account-main"><strong>{account.displayName}</strong><span>{account.email}</span></div>
      <span className={`account-status account-${account.status}`}>{account.status === 'active' ? 'Approved' : account.status === 'pending' ? 'Pending approval' : 'Disabled'}</span>
      <span className="account-role">{account.role}</span>
      {account.id !== currentUser.id && account.role !== 'administrator' && <button className={`button ${account.status === 'active' ? 'button-outline-danger' : 'button-outline'}`} disabled={pendingId === account.id} onClick={() => void setStatus(account, account.status === 'active' ? 'disabled' : 'active')}>{pendingId === account.id ? <LoaderCircle className="spin" size={15} /> : account.status === 'active' ? <X size={15} /> : <Check size={15} />}{account.status === 'active' ? 'Disable' : 'Approve'}</button>}
    </article>)}</div>}
    <div className="access-footnote"><ShieldCheck size={16} /> First account is the administrator. New sign-ups remain pending until approved here. Disabling an account ends its active sessions.</div>
  </section></div>;
}

function NavItem({ active, label, icon, count, onClick }: { active: boolean; label: string; icon: React.ReactNode; count?: number; onClick: () => void }) {
  return <button className={`nav-item ${active ? 'nav-active' : ''}`} onClick={onClick}>{icon}<span>{label}</span>{count !== undefined && <small>{count}</small>}</button>;
}

function Stat({ label, value, detail, icon, tone = 'navy' }: { label: string; value: string | number; detail: string; icon: React.ReactNode; tone?: 'navy' | 'amber' | 'teal' | 'red' }) {
  return <div className="stat-block"><div className={`stat-icon stat-${tone}`}>{icon}</div><div className="stat-text"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
}

function SectionTitle({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return <div className="section-title"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>;
}

const DEFAULT_JOURNAL_CSV = `timestamp,txn_ref,atm_id,status
2026-11-26T14:20:06,TXN-RJP-8841,ATM-02,DISPUTED_SKIM_ALERT
2026-11-26T14:20:14,TXN-RJP-8842,ATM-02,CASH_WITHDRAWAL`;

function CaseDesk({ clips, cameras, analyses, health, events, onAddOrChange, onDeleteClip, onReview, onRefresh, onToast }: {
  clips: Clip[]; cameras: CameraSlot[]; analyses: Analysis[]; health: Health | null;
  events: EventItem[]; onAddOrChange: (cameraId: string, replaceClipId?: string) => void;
  onDeleteClip: (clip: Clip) => void; onReview: (id: string) => void; onRefresh: () => void; onToast: (toast: Toast) => void;
}) {
  const [clipId, setClipId] = useState('');
  const [mode, setMode] = useState<'clip' | 'absolute'>('clip');
  const [time, setTime] = useState('00:00:04');
  const [clipStart, setClipStart] = useState('2026-11-26T14:20:00');
  const [reference, setReference] = useState('');
  const [caseRef, setCaseRef] = useState('');
  const [windowSeconds, setWindowSeconds] = useState(30);
  const [submitting, setSubmitting] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [journalCsv, setJournalCsv] = useState(DEFAULT_JOURNAL_CSV);
  const [journalRows, setJournalRows] = useState<JournalRow[]>([]);
  const [journalBusy, setJournalBusy] = useState(false);

  useEffect(() => { if (!clips.some((clip) => clip.id === clipId)) setClipId(clips[0]?.id || ''); }, [clips, clipId]);

  const loadDemo = async () => {
    setDemoBusy(true);
    try {
      const demo = await api.loadDemo();
      setJournalCsv(demo.sampleJournalCsv);
      setTime(demo.recommendedClipTime);
      setClipStart(demo.recommendedClipStart);
      setReference('TXN-RJP-8841');
      setCaseRef('FIR-JPR-2026-PS04');
      onToast({ kind: 'success', message: '2 demo clips (ATM-01, ATM-02) loaded; ATM-03 & ATM-04 remain open for your footage/IP Webcam.' });
      onRefresh();
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not load demo dataset.' });
    } finally {
      setDemoBusy(false);
    }
  };

  const matchJournal = async (autoQueue: boolean) => {
    if (!clipId) { onToast({ kind: 'error', message: 'Select or upload a clip first.' }); return; }
    setJournalBusy(true);
    try {
      const res = await api.matchJournal({
        clip_id: clipId,
        clip_start_time: clipStart || '2026-11-26T14:20:00',
        csv_text: journalCsv,
        window_seconds: windowSeconds,
        auto_queue: autoQueue,
      });
      setJournalRows(res.rows);
      onToast({
        kind: 'success',
        message: autoQueue && res.queuedAnalyses.length
          ? `Matched ${res.inClipCount} journal row(s) and queued ${res.queuedAnalyses.length} investigation(s).`
          : `Matched ${res.inClipCount} of ${res.totalRows} journal transactions inside this clip.`,
      });
      if (autoQueue && res.queuedAnalyses.length) {
        onRefresh();
        onReview(res.queuedAnalyses[0]);
      }
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Journal matching failed.' });
    } finally {
      setJournalBusy(false);
    }
  };

  const createCase = async (event: FormEvent) => {
    event.preventDefault();
    if (!clipId) { onToast({ kind: 'error', message: 'Upload an ATM clip before starting analysis.' }); return; }
    if (mode === 'absolute' && !clipStart) { onToast({ kind: 'error', message: 'Enter the CCTV clip start timestamp to link the bank transaction.' }); return; }
    setSubmitting(true);
    try {
      const result = await api.analyze({
        clip_id: clipId,
        transaction_time: time,
        time_mode: mode,
        clip_start_time: mode === 'absolute' ? clipStart : '',
        transaction_ref: reference,
        case_ref: caseRef,
        window_seconds: windowSeconds,
      });
      onToast({ kind: 'success', message: 'Analysis started on the local machine.' });
      onReview(result.id);
    } catch (error) {
      onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not start analysis.' });
    } finally { setSubmitting(false); }
  };

  const peopleCount = analyses.reduce((count, item) => count + (item.result?.peopleSeen || 0), 0);
  const reviewedCount = analyses.reduce((count, item) => count + (item.result?.candidateCount || 0), 0);

  return (
    <>
      <div className="stat-row">
        <Stat label="Footage clips" value={clips.length} detail="In local evidence vault" icon={<FileVideo2 size={19} />} />
        <Stat label="Completed reviews" value={analyses.filter((item) => item.status === 'completed').length} detail={`${analyses.filter((item) => item.status === 'running').length} currently processing`} icon={<FileSearch size={19} />} tone="teal" />
        <Stat label="Person tracks" value={peopleCount} detail="Across completed clips" icon={<UsersRound size={19} />} tone="amber" />
        <Stat label="Face candidates" value={reviewedCount} detail="SFace 128-D indexed" icon={<ScanFace size={19} />} tone="red" />
      </div>

      <div className="desk-grid">
        <section className="panel intake-panel">
          <SectionTitle
            title="Start an investigation"
            detail="Link one clip to the transaction time."
            action={
              <button type="button" className="button button-compact demo-cta" onClick={() => void loadDemo()} disabled={demoBusy}>
                {demoBusy ? <LoaderCircle size={14} className="spin" /> : <Sparkles size={14} />} Load Demo (2 Clips)
              </button>
            }
          />
          <form className="intake-form" onSubmit={createCase}>
            <label className="field-label" htmlFor="clip-select">ATM footage</label>
            <div className="select-wrap"><FileVideo2 size={17} /><select id="clip-select" name="clip_id" value={clipId} onChange={(event) => setClipId(event.target.value)} disabled={!clips.length}>
              {clips.length ? clips.map((clip) => <option key={clip.id} value={clip.id}>{clip.cameraId} · {clip.filename}</option>) : <option value="">No clips uploaded</option>}
            </select><ChevronDown size={16} /></div>
            {!clips.length && <button type="button" className="inline-link" onClick={() => onAddOrChange('ATM-01')}><Upload size={14} /> Add footage or IP Webcam</button>}

            <div className="form-row between-row">
              <label className="field-label" htmlFor="transaction-time">Transaction time</label>
              <div className="segmented-control" aria-label="Time format">
                <button type="button" className={mode === 'clip' ? 'segment-active' : ''} onClick={() => { setMode('clip'); setTime('00:00:04'); }}>Clip time</button>
                <button type="button" className={mode === 'absolute' ? 'segment-active' : ''} onClick={() => { setMode('absolute'); setTime('2026-11-26T14:20:06'); }}>Bank time</button>
              </div>
            </div>
            {mode === 'clip' ? <div className="time-entry"><Clock3 size={17} /><input id="transaction-time-text" name="transaction_time" type="text" inputMode="numeric" pattern="\d{2,3}:\d{2}:\d{2}" placeholder="HH:MM:SS" value={time} onChange={(event) => setTime(event.target.value)} required /><span>HH:MM:SS</span></div> : <div className="time-entry"><Clock3 size={17} /><input id="transaction-time" name="transaction_time" type="datetime-local" value={time} onChange={(event) => setTime(event.target.value)} required /></div>}
            {mode === 'absolute' && <label className="field-group" htmlFor="clip-start-time"><span className="field-label">CCTV clip start timestamp</span><input id="clip-start-time" name="clip_start_time" type="datetime-local" value={clipStart} onChange={(event) => setClipStart(event.target.value)} required /></label>}

            <div className="form-grid-two">
              <label className="field-group" htmlFor="case-ref"><span className="field-label">Case / FIR Ref <i>optional</i></span><input id="case-ref" name="case_ref" type="text" maxLength={40} placeholder="e.g. FIR-JPR-2026-0412" value={caseRef} onChange={(event) => setCaseRef(event.target.value)} /></label>
              <label className="field-group" htmlFor="window-seconds"><span className="field-label">Search window</span><select id="window-seconds" name="window_seconds" value={windowSeconds} onChange={(event) => setWindowSeconds(Number(event.target.value))}><option value={15}>±15 seconds</option><option value={30}>±30 seconds</option><option value={60}>±60 seconds</option><option value={120}>±2 minutes</option><option value={300}>±5 minutes</option></select></label>
            </div>
            <label className="field-group" htmlFor="txn-ref"><span className="field-label">Bank Transaction Ref / RRN <i>optional</i></span><input id="txn-ref" name="transaction_ref" type="text" maxLength={40} placeholder="e.g. TXN-RJP-8841" value={reference} onChange={(event) => setReference(event.target.value)} /></label>
            <div className="form-callout"><ShieldCheck size={17} /><span>Frame ranking supports review. It does not identify a person or establish guilt.</span></div>
            <button className="button button-primary intake-submit" disabled={submitting || !clips.length || !health} type="submit">{submitting ? <LoaderCircle size={17} className="spin" /> : <ScanFace size={17} />}{submitting ? 'Starting local analysis…' : 'Find best face frames'}<ArrowRight size={17} /></button>
          </form>
        </section>

        <section className="panel camera-panel">
          <SectionTitle title="Four ATM evidence channels" detail="Add footage / IP Webcam, change clips, or delete per slot" action={<span className="recorded-chip"><span /> {clips.length} CLIPS</span>} />
          <CameraWall cameras={cameras} onAddOrChange={onAddOrChange} onDeleteClip={onDeleteClip} compact />
          <div className="camera-footnote"><LockKeyhole size={14} /> No live bank CCTV connection · no cloud stream proxy</div>
        </section>
      </div>

      <section className="panel journal-panel">
        <SectionTitle
          title="ATM Transaction Journal (EJ / Bank CSV) Matcher"
          detail="Paste bank switch / ATM EJ CSV rows to automatically link disputed withdrawals to CCTV offsets"
          action={<span className="sorted-indicator"><FileSpreadsheet size={14} /> BATCH LINKER</span>}
        />
        <div className="journal-grid">
          <div className="intake-form">
            <label className="field-group" htmlFor="journal-clip-start"><span className="field-label">Clip start timestamp (for journal alignment)</span><input id="journal-clip-start" name="journal_clip_start" type="datetime-local" value={clipStart} onChange={(e) => setClipStart(e.target.value)} /></label>
            <label className="field-group" htmlFor="journal-csv"><span className="field-label">Transaction Journal CSV</span>
              <textarea id="journal-csv" name="journal_csv" className="journal-textarea" value={journalCsv} onChange={(e) => setJournalCsv(e.target.value)} />
            </label>
            <div className="form-row">
              <button type="button" className="button button-outline button-compact" disabled={journalBusy || !clips.length} onClick={() => void matchJournal(false)}>
                <FileSearch size={15} /> Preview Matches
              </button>
              <button type="button" className="button button-primary button-compact" disabled={journalBusy || !clips.length} onClick={() => void matchJournal(true)}>
                {journalBusy ? <LoaderCircle size={15} className="spin" /> : <ScanFace size={15} />} Auto-Queue Disputed
              </button>
            </div>
          </div>
          <div>
            {journalRows.length ? (
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>TXN REF</th><th>TIMESTAMP</th><th>OFFSET</th><th>STATUS</th><th>MATCH</th></tr></thead>
                  <tbody>
                    {journalRows.map((row) => (
                      <tr key={`${row.row}-${row.txnRef}`}>
                        <td><strong>{row.txnRef}</strong><span>{row.atmId}</span></td>
                        <td className="mono-data">{row.timestamp}</td>
                        <td className="mono-data">{row.offsetSeconds >= 0 ? `+${row.offsetSeconds}s` : '—'}</td>
                        <td>{row.status}{row.disputed && <span className="journal-badge-disputed">FLAGGED</span>}</td>
                        <td>
                          {row.analysisId ? (
                            <button className="text-button" onClick={() => onReview(row.analysisId!)}>Open review <ArrowRight size={13} /></button>
                          ) : (
                            <span className={row.inClip ? 'journal-badge-in' : 'journal-badge-out'}>{row.inClip ? 'IN CLIP' : 'OUTSIDE'}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyLine icon={<FileSpreadsheet size={18} />} title="Journal matcher ready" detail="Click 'Preview Matches' or 'Auto-Queue Disputed' to link bank switch timestamps against the selected CCTV clip." />
            )}
          </div>
        </div>
      </section>

      <div className="lower-grid">
        <section className="panel recent-panel">
          <SectionTitle title="Recent investigations" detail="Latest analysis activity" action={<button className="text-button" onClick={() => onReview(analyses[0]?.id || '')} disabled={!analyses.length}>View all <ArrowRight size={14} /></button>} />
          {analyses.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>CLIP / CAMERA</th><th>TRANSACTION TIME</th><th>RESULT</th><th>STATUS</th><th /></tr></thead><tbody>
            {analyses.slice(0, 5).map((item) => <tr key={item.id} onClick={() => onReview(item.id)} className="clickable-row"><td><strong>{item.clipName}</strong><span>{item.caseRef || clips.find((clip) => clip.id === item.clipId)?.cameraId || 'Local clip'}</span></td><td className="mono-data">{item.transactionTime}</td><td>{item.result?.candidateCount ?? '—'} candidate frames</td><td><StatusBadge status={item.status} /></td><td><ChevronRight size={16} /></td></tr>)}
          </tbody></table></div> : <EmptyLine icon={<History size={18} />} title="No investigation records yet" detail="Upload a clip or click 'Load Demo (2 Clips)' to run the first transaction-time review." />}
        </section>

        <section className="panel activity-panel">
          <SectionTitle title="Local activity &amp; alerts" detail="Recent system events" action={<span className="activity-clock"><Activity size={14} /> {events.length} EVENTS</span>} />
          {events.length ? <div className="activity-list">{events.slice(0, 5).map((event) => <div className="activity-item" key={event.id}><span className={`activity-pin ${event.severity === 'warning' || event.severity === 'critical' ? 'pin-amber' : ''}`} /><div><strong>{event.message}</strong><time>{new Date(event.occurredAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</time></div></div>)}</div> : <EmptyLine icon={<Activity size={18} />} title="Activity will appear here" detail="Uploads, analyses and review decisions are recorded locally." />}
        </section>
      </div>
      <div className="engine-strip"><div className="engine-left"><span className={`engine-dot ${health ? 'engine-ready' : ''}`} /><strong>LOCAL ANALYSIS ENGINE</strong><span>•</span><span>{health?.models.person || 'Person detector'}</span><span>•</span><span>{health?.models.face || 'Face detector'}</span><span>•</span><span>{health?.models.embedding || 'Embeddings'}</span></div><button className="text-button" onClick={() => window.open('/api/docs', '_blank', 'noopener,noreferrer')}>API docs <ArrowRight size={14} /></button></div>
    </>
  );
}

function CameraWall({ cameras, onAddOrChange, onDeleteClip, compact = false }: {
  cameras: CameraSlot[];
  onAddOrChange: (cameraId: string, replaceClipId?: string) => void;
  onDeleteClip: (clip: Clip) => void;
  compact?: boolean;
}) {
  const labels = [
    { id: 'ATM-01', label: 'Entry view', icon: <Eye size={16} /> },
    { id: 'ATM-02', label: 'Keypad view', icon: <Crosshair size={16} /> },
    { id: 'ATM-03', label: 'Cash slot', icon: <Database size={16} /> },
    { id: 'ATM-04', label: 'Exit view', icon: <ArrowDownRight size={16} /> },
  ];
  return <div className={`camera-grid ${compact ? 'camera-grid-compact' : ''}`}>
    {labels.map((item) => {
      const slot = cameras.find((camera) => camera.id === item.id);
      const clip = slot?.clips?.[0];
      return <article className={`camera-tile ${clip ? 'camera-has-clip' : ''}`} key={item.id}>
        <div className="camera-video-area">
          {clip ? clip.previewReady ? <video src={clip.videoUrl} poster={clip.posterUrl} muted controls playsInline preload="none" aria-label={`${item.id} ${item.label} local recording`} /> : <div className="camera-poster-preview"><img src={clip.posterUrl} alt={`${item.id} ${item.label} video poster`} /><span>Playback needs FFmpeg H.264 conversion</span></div> : <div className="camera-empty"><Camera size={20} /><span>No local clip assigned</span><button onClick={() => onAddOrChange(item.id)}><Plus size={14} /> Add footage / IP cam</button></div>}
          <span className={`camera-state ${clip ? 'camera-recorded' : ''}`}><i />{clip ? (clip.previewReady ? 'RECORDED' : 'POSTER ONLY') : 'EMPTY'}</span>
        </div>
        <div className="camera-meta">
          <div className="camera-label-icon">{item.icon}</div>
          <div>
            <strong>{item.id} <span>{item.label}</span></strong>
            <small>{clip ? `${clip.filename} · ${formatDuration(clip.duration)}` : 'Waiting for file or IP Webcam'}</small>
          </div>
          <div className="camera-actions-inline">
            <button
              className="icon-button"
              aria-label={clip ? `Change footage on ${item.id}` : `Add footage to ${item.id}`}
              title={clip ? 'Change footage or connect IP Webcam' : 'Add footage or connect IP Webcam'}
              onClick={() => onAddOrChange(item.id, clip?.id || '')}
            >
              {clip ? <Pencil size={14} /> : <Upload size={15} />}
            </button>
            {clip && (
              <button
                className="icon-button danger-hover"
                aria-label={`Delete footage from ${item.id}`}
                title="Delete footage"
                onClick={() => onDeleteClip(clip)}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>
      </article>;
    })}
  </div>;
}

function EmptyLine({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <div className="empty-line"><span>{icon}</span><div><strong>{title}</strong><p>{detail}</p></div></div>;
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = { running: 'Processing', completed: 'Ready for review', failed: 'Needs attention', queued: 'Queued' };
  return <span className={`status-badge badge-${status}`}><i />{labels[status] || status}</span>;
}

function Library({ clips, cameras, onAddOrChange, onDelete }: {
  clips: Clip[];
  cameras: CameraSlot[];
  onAddOrChange: (id: string, replaceClipId?: string) => void;
  onDelete: (clip: Clip) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState('');
  const [integrity, setIntegrity] = useState<Record<string, { verified: boolean; checkedAt: string; notice: string }>>({});
  const [checking, setChecking] = useState('');
  const [guidance, setGuidance] = useState<{ vendor: string; steps: string }[]>([]);
  const [showDvr, setShowDvr] = useState(false);

  useEffect(() => {
    void api.dvrGuidance().then((res) => setGuidance(res.guidance)).catch(() => {});
  }, []);

  const verify = async (clip: Clip) => {
    setChecking(clip.id);
    try {
      const result = await api.integrity(clip.id);
      setIntegrity((current) => ({ ...current, [clip.id]: result }));
    } catch (error) {
      setIntegrity((current) => ({ ...current, [clip.id]: { verified: false, checkedAt: new Date().toISOString(), notice: error instanceof Error ? error.message : 'Hash verification failed.' } }));
    } finally { setChecking(''); }
  };
  return <>
    <div className="library-callout"><div className="callout-mark"><ShieldCheck size={20} /></div><div><strong>Local vault with SHA-256 &amp; container forensics</strong><span>Supports MP4, AVI, MOV, MKV, WMV, FLV, MPEG, MPG, plus unencrypted DAV/H264/TS DVR exports normalized locally via FFmpeg.</span></div><button className="button button-outline button-compact" onClick={() => setShowDvr((v) => !v)}>{showDvr ? 'Hide DVR Guide' : 'DVR/NVR Export Guide'}</button></div>
    {showDvr && (
      <section className="panel library-panel">
        <SectionTitle title="Proprietary DVR / NVR Export Instructions" detail="If an ATM DVR export is encrypted or vendor-wrapped, convert using these local steps" />
        <div className="dvr-guidance-grid">
          {guidance.map((g) => (
            <div className="dvr-card" key={g.vendor}>
              <strong>{g.vendor}</strong>
              <span>{g.steps}</span>
            </div>
          ))}
        </div>
      </section>
    )}
    <section className="panel library-panel"><SectionTitle title="ATM evidence channels" detail="Add, replace, or delete footage per slot; or attach your IP Webcam." action={<button className="button button-primary button-compact" onClick={() => onAddOrChange('ATM-01')}><Upload size={15} /> Add footage / IP Cam</button>} />
      <CameraWall cameras={cameras} onAddOrChange={onAddOrChange} onDeleteClip={onDelete} />
    </section>
    <section className="panel library-files"><SectionTitle title="Uploaded footage &amp; container forensics" detail={`${clips.length} clip${clips.length === 1 ? '' : 's'} in this workspace`} />
      {clips.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>FILE &amp; FORENSICS</th><th>CAMERA</th><th>DURATION</th><th>RESOLUTION</th><th>SHA-256 · SOURCE</th><th>INTEGRITY</th><th>UPLOADED</th><th /></tr></thead><tbody>{clips.map((clip) => <tr key={clip.id}><td><div className="file-cell"><FileVideo2 size={17} /><div><strong>{clip.filename}</strong><span>{clip.codec.toUpperCase()} · {clip.fps} FPS · {clip.forensics?.container?.bitRateKbps ? `${clip.forensics.container.bitRateKbps} kbps` : formatBytes(clip.sizeBytes)}{clip.forensics?.continuity?.spliceCues ? ` · ${clip.forensics.continuity.spliceCues} splice cue(s)` : ''}</span></div></div></td><td><span className="camera-id-pill">{clip.cameraId}</span></td><td className="mono-data">{formatDuration(clip.duration)}</td><td>{clip.width} × {clip.height}</td><td><code className="hash-code" title={clip.sha256}>{clip.sha256.slice(0, 18)}…</code></td><td>{integrity[clip.id] ? <span className={`integrity-status ${integrity[clip.id].verified ? 'integrity-ok' : 'integrity-mismatch'}`} title={integrity[clip.id].notice}><i />{integrity[clip.id].verified ? 'Verified' : 'Mismatch'}</span> : <button className="verify-button" disabled={checking === clip.id} onClick={() => void verify(clip)}>{checking === clip.id ? <LoaderCircle size={13} className="spin" /> : <ShieldCheck size={13} />} Verify</button>}</td><td>{new Date(clip.uploadedAt).toLocaleDateString('en-IN')}</td><td className="delete-cell">{confirmDelete === clip.id ? <span className="confirm-delete"><button onClick={() => { onDelete(clip); setConfirmDelete(''); }}>Remove</button><button aria-label="Cancel remove" onClick={() => setConfirmDelete('')}><X size={15} /></button></span> : <button className="icon-button danger-hover" aria-label={`Remove ${clip.filename}`} onClick={() => setConfirmDelete(clip.id)}><Trash2 size={16} /></button>}</td></tr>)}</tbody></table></div> : <EmptyLine icon={<FolderOpen size={18} />} title="No video files uploaded" detail="Upload MP4, AVI, MOV, MKV, WMV, FLV, MPEG, or DAV/H264 footage to start a review." />}
    </section>
  </>;
}

function Review({ analysisId, analysisSummary, canAnchor, onOpenSearch, onToast, onRefresh }: {
  analysisId: string; analysisSummary?: Analysis; canAnchor: boolean; onOpenSearch: (candidateId: string) => void; onToast: (toast: Toast) => void; onRefresh: () => void;
}) {
  const [record, setRecord] = useState<Analysis | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [anchoring, setAnchoring] = useState(false);
  const [showEnhanced, setShowEnhanced] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [brightness, setBrightness] = useState(100);
  const [contrast, setContrast] = useState(100);
  const [suspectLabel, setSuspectLabel] = useState('Suspect-01');
  const [arming, setArming] = useState(false);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const characteristicsRef = useRef<HTMLElement>(null);
  const [observationTime, setObservationTime] = useState('');
  const [visibility, setVisibility] = useState<FaceVisibility>('unavailable');
  const [observationNote, setObservationNote] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [relatedIncidents, setRelatedIncidents] = useState<LiveIncident[]>([]);
  const [savingObservation, setSavingObservation] = useState(false);

  const load = useCallback(async () => {
    if (!analysisId) return;
    try { const result = await api.analysis(analysisId); setRecord(result); }
    catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not load analysis.' }); }
  }, [analysisId, onToast]);

  useEffect(() => {
    setRecord(null);
    setSelectedId('');
    setShowEnhanced(false);
    setBrightness(100);
    setContrast(100);
    setObservationTime('');
    setVisibility('unavailable');
    setObservationNote('');
    setIncidentId('');
    void load();
  }, [analysisId, load]);

  useEffect(() => {
    if (!analysisId || (record && (record.status === 'completed' || record.status === 'failed'))) return;
    const timer = window.setInterval(() => void load(), 2200);
    return () => window.clearInterval(timer);
  }, [analysisId, record?.status, load]);

  useEffect(() => {
    let active = true;
    setRelatedIncidents([]);
    const channel = record?.cameraId?.replace(/^ATM-/, '');
    if (channel && record?.status === 'completed') {
      void api.liveIncidents().then((items) => {
        if (active) setRelatedIncidents(items.filter((item) => item.cameraId.replace(/^CAM-/, '') === channel));
      }).catch(() => {});
    }
    return () => { active = false; };
  }, [analysisId, record?.cameraId, record?.status]);

  const selected = record?.candidates.find((candidate) => candidate.id === selectedId) || record?.candidates[0];
  useEffect(() => { if (selected) setNote(selected.note || ''); }, [selected?.id]);

  const mark = async (status: Candidate['reviewStatus']) => {
    if (!selected) return;
    setBusy(true);
    try { await api.review(selected.id, status, note); await load(); onRefresh(); onToast({ kind: 'success', message: `Candidate marked ${status}. Review action recorded.` }); }
    catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save review.' }); }
    finally { setBusy(false); }
  };

  const armWatchlist = async () => {
    if (!selected || !suspectLabel.trim()) return;
    setArming(true);
    try {
      await api.addToWatchlist(selected.id, suspectLabel.trim(), record?.caseRef || '');
      onRefresh();
      onToast({ kind: 'success', message: `Armed '${suspectLabel.trim()}' on live 4-camera & IP Webcam SFace watchlist!` });
    } catch (err) {
      onToast({ kind: 'error', message: err instanceof Error ? err.message : 'Could not arm watchlist.' });
    } finally {
      setArming(false);
    }
  };

  const inspectSourceAt = (seconds: number) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = seconds;
    videoRef.current.pause();
    videoRef.current.scrollIntoView({ block: 'nearest' });
  };

  const saveObservation = async (event: FormEvent) => {
    event.preventDefault();
    if (!observationTime.trim()) return;
    setSavingObservation(true);
    try {
      await api.recordFootageObservation(analysisId, { time: Number(observationTime), visibility, note: observationNote.trim(), incidentId: incidentId.trim() });
      setObservationNote('');
      setIncidentId('');
      await load();
      onRefresh();
      onToast({ kind: 'success', message: 'Footage observation saved to the case and audit log.' });
    } catch (error) {
      onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save footage observation.' });
    } finally { setSavingObservation(false); }
  };

  const anchorEvidence = async () => {
    setAnchoring(true);
    try {
      const bundle = await api.publishBlockchainEvidence(analysisId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `drishti-${analysisId}-blockchain.json`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      onToast({ kind: 'success', message: 'Fingerprint submitted. Verify the downloaded blockchain bundle in Security.' });
      onRefresh();
    } catch (error) {
      onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not submit the fingerprint.' });
    } finally {
      setAnchoring(false);
    }
  };

  if (!analysisId) return <section className="panel no-analysis"><ScanFace size={32} /><h2>Select an investigation</h2><p>Choose a completed investigation from Case desk to review the extracted candidates.</p></section>;
  const active = record || analysisSummary;
  const alerts = record?.result?.alerts || [];
  const bestCandidate = record?.candidates.reduce<Candidate | undefined>(
    (best, candidate) => (!best || candidate.score > best.score ? candidate : best),
    undefined,
  );
  const assessmentTime = bestCandidate?.time ?? record?.result?.windowStart ?? 0;
  const missingFaces = record?.result?.personWithoutFaceSamples;
  const visibilityLabels: Record<FaceVisibility, string> = { visible: 'Face visible', covered: 'Face visibly covered', unavailable: 'Face unavailable for review' };

  return <>
    <div className="review-context-bar"><div className="context-icon"><FileVideo2 size={18} /></div><div><strong>{active?.clipName || 'Loading clip record…'}</strong><span>{active?.caseRef ? `${active.caseRef} · ` : ''}{active?.transactionRef || 'No transaction reference'} · {active?.timeMode === 'absolute' ? 'Bank timestamp' : 'Clip-relative time'} {active?.transactionTime}</span></div><div className="context-window"><Clock3 size={15} /> ±{active?.windowSeconds || 0}s window</div><StatusBadge status={record?.status || active?.status || 'running'} />{record?.status === 'completed' && <><a className="button button-outline button-compact" href={`/api/evidence/${record.id}/manifest.json`} download><FileCode2 size={15} /> Manifest</a><a className="button button-outline button-compact" href={`/api/evidence/${record.id}/bsa63.pdf`} download><BadgeCheck size={15} /> BSA Sec 63</a><a className="button button-outline button-compact evidence-download" href={`/api/evidence/${record.id}.pdf`} download><Download size={15} /> PDF</a><a className="button button-primary button-compact" href={`/api/evidence/${record.id}/bundle.zip`} download><HardDrive size={15} /> Case Bundle (.zip)</a></>}</div>
    {record?.status === 'running' && <div className="processing-banner"><LoaderCircle size={18} className="spin" /><div><strong>Reviewing the transaction window locally</strong><span>Detecting people, checking occlusion/shoulder-surfing, and indexing SFace 128-D embeddings.</span></div><span className="process-time">ANALYSIS RUNNING</span></div>}
    {record?.status === 'failed' && <div className="error-banner"><AlertCircle size={18} /><div><strong>Analysis could not complete</strong><span>{record.error}</span></div></div>}
    {canAnchor && record?.status === 'completed' && <button type="button" className="button button-outline button-compact" disabled={anchoring} onClick={() => void anchorEvidence()}><Fingerprint size={15} />{anchoring ? 'Submitting fingerprint…' : 'Anchor manifest on blockchain'}</button>}
    {record?.status === 'completed' && <button type="button" className="button button-outline button-compact" onClick={() => characteristicsRef.current?.focus()}><Eye size={15} /> Physical characteristics</button>}
    {alerts.length > 0 && (
      <div className="alert-stack">
        {alerts.map((alert, idx) => (
          <div className="alert-banner-warn" key={`${alert.kind}-${idx}`}>
            <AlertTriangle size={17} />
            <strong>{alert.message}</strong>
          </div>
        ))}
      </div>
    )}
    {record?.status === 'completed' && <section className="panel clip-player-panel footage-review-panel">
      <SectionTitle title="Face visibility and case handoff" detail={missingFaces === undefined
        ? 'This analysis predates frame-by-frame visibility sampling. You can still record an observation.'
        : `${missingFaces.length} of ${record.result.personFrames ?? 0} sampled frames with a detected person had no face detection.`}
        action={<a className="button button-outline button-compact" href={`/api/evidence/${record.id}/bundle.zip?include_original=true`} download><Download size={15} /> Case bundle with original footage</a>} />
      {missingFaces && missingFaces.length > 0 && <p className="footage-assessment-summary">A missed detection has several possible causes. <button type="button" className="text-button" onClick={() => { inspectSourceAt(missingFaces[0]); setObservationTime(String(missingFaces[0])); }}>Inspect first frame at {formatDuration(missingFaces[0])}</button></p>}
      <form className="footage-observation-form" onSubmit={(event) => void saveObservation(event)}>
        <label>Clip time (seconds)<input type="number" min="0" step="0.001" required value={observationTime} onChange={(e) => setObservationTime(e.target.value)} /></label>
        <button type="button" className="button button-outline button-compact" onClick={() => { if (videoRef.current?.readyState) { videoRef.current.pause(); setObservationTime(videoRef.current.currentTime.toFixed(3)); } }}>Use source player time</button>
        <label>Investigator observation<select value={visibility} onChange={(e) => setVisibility(e.target.value as FaceVisibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        {relatedIncidents.length > 0 && <label>Related incident on this camera (optional)<select value={incidentId} onChange={(e) => setIncidentId(e.target.value)}><option value="">Choose only if you verified the link</option>{relatedIncidents.map((incident) => <option key={incident.id} value={incident.id}>{new Date(incident.occurredAt).toLocaleString('en-IN')} · {incident.kind}</option>)}</select></label>}
        <label>Notes (optional)<input value={observationNote} maxLength={500} onChange={(e) => setObservationNote(e.target.value)} placeholder="What is visible at this time?" /></label>
        <button className="button button-primary button-compact" type="submit" disabled={savingObservation}>{savingObservation ? 'Saving…' : 'Save observation'}</button>
      </form>
      {(record.observations ?? []).map((ob) => <p key={ob.id} className="footage-assessment-summary"><button type="button" className="text-button" onClick={() => inspectSourceAt(ob.time)}>{formatDuration(ob.time)}</button> · <strong>{visibilityLabels[ob.visibility]}</strong>{ob.note && ` · ${ob.note}`}{ob.incident && <> · <a href={`/api/live-incidents/${ob.incident.id}/image`}>Linked incident snapshot</a></>}</p>)}
    </section>}
    <div className="review-grid">
      <section className="panel candidate-panel"><SectionTitle title="Face frame candidates" detail={record?.status === 'completed' ? `${record.candidates.length} frames · sorted by quality score (${record.result.embeddingModel || 'local'})` : 'Waiting for analysis results'} action={record?.status === 'completed' && record.candidates.length > 0 ? <span className="sorted-indicator"><SlidersHorizontal size={14} /> BEST FIRST</span> : undefined} />
        {record?.status === 'completed' && record.candidates.length ? <div className="candidate-grid">{record.candidates.map((candidate, index) => <button className={`candidate-card ${selected?.id === candidate.id ? 'candidate-selected' : ''}`} onClick={() => setSelectedId(candidate.id)} key={candidate.id}>
          <div className="candidate-image-wrap"><img src={candidate.imageUrl} alt={`Face candidate at ${candidate.timeLabel}`} /><span className="candidate-rank">{String(index + 1).padStart(2, '0')}</span><span className={`quality-badge ${candidate.score >= 75 ? 'quality-high' : candidate.score >= 50 ? 'quality-mid' : 'quality-low'}`}>{Math.round(candidate.score)}<small> / 100</small></span></div>
          <div className="candidate-card-meta"><strong>{candidate.timeLabel}</strong><span>TRACK {String(candidate.trackId).padStart(2, '0')}</span></div>
          <div className="candidate-mini-metrics"><i style={{ width: `${candidate.score}%` }} /></div>
          {candidate.flags.length > 0 && <div className="candidate-flags">{candidate.flags.slice(0, 2).map((flag) => <span key={flag}>{flag}</span>)}</div>}
        </button>)}</div> : record?.status === 'completed' ? <div className="no-candidates"><div className="no-candidate-icon"><ScanFace size={24} /></div><h3>No face candidates found</h3><p>Try a wider time window or a clearer clip export. Low resolution, occlusion and camera angle can affect detection.</p><div className="no-candidate-meta"><span>{record.result.sampledFrames || 0} frames sampled</span><span>{record.result.peopleSeen || 0} person tracks</span></div></div> : <div className="candidate-loading"><LoaderCircle size={22} className="spin" /><span>Candidate frames appear here when analysis finishes.</span></div>}
      </section>

      <aside className="review-side-stack">
        <section className="panel selected-panel"><SectionTitle title="Selected frame" detail={selected ? `Track ${String(selected.trackId).padStart(2, '0')} · ${selected.timeLabel}` : 'Choose a candidate'} />
          {selected ? <>
            <div className="enhance-toggle">
              <div className="segmented-control" aria-label="Image view mode">
                <button type="button" className={!showEnhanced ? 'segment-active' : ''} onClick={() => setShowEnhanced(false)}>Original Raw</button>
                <button type="button" className={showEnhanced ? 'segment-active' : ''} onClick={() => setShowEnhanced(true)}>Enhanced (2×)</button>
              </div>
              <button type="button" className="text-button" onClick={() => setShowFilters((v) => !v)}><SlidersHorizontal size={13} /> Light</button>
              <button type="button" className="text-button" onClick={() => setShowPrivacyModal(true)} title="Blur bystander faces for privacy-compliant sharing">
                <EyeOff size={14} /> Privacy Frame
              </button>
            </div>
            {showEnhanced && <div className="enhance-note">ENHANCED FOR REVIEW ONLY (CLAHE + Unsharp 2×). Original unedited crop is preserved and hashed.</div>}
            {showFilters && (
              <div className="forensic-sliders">
                <div className="forensic-slider-row"><label htmlFor="light-brightness">Brightness</label><input id="light-brightness" name="brightness" type="range" min={60} max={200} value={brightness} onChange={(e) => setBrightness(Number(e.target.value))} /><strong>{brightness}%</strong></div>
                <div className="forensic-slider-row"><label htmlFor="light-contrast">Contrast</label><input id="light-contrast" name="contrast" type="range" min={60} max={220} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} /><strong>{contrast}%</strong></div>
              </div>
            )}
            <div className="selected-image"><img style={{ filter: `brightness(${brightness}%) contrast(${contrast}%)` }} src={showEnhanced ? selected.enhancedUrl : selected.imageUrl} alt={showEnhanced ? 'Enhanced candidate face crop' : 'Selected candidate face crop'} /><span className="selected-score">{Math.round(selected.score)}<small> QUALITY</small></span></div>
            <button className="text-button frame-link" onClick={() => inspectSourceAt(selected.time)}><Play size={14} /> Find this time in clip <span>{selected.timeLabel}</span></button>
            <QualityBars metrics={selected.metrics} />
            <div className="review-flags"><strong>Reliability flags</strong>{selected.flags.length ? selected.flags.map((flag) => <span className="flag-chip" key={flag}><AlertCircle size={13} />{flag}</span>) : <span className="clear-flag"><Check size={13} /> No occlusion or quality flags</span>}</div>
            <label className="review-note" htmlFor="investigator-note"><span>Investigator note</span><textarea id="investigator-note" name="note" value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Add an observation or comparison note…" /></label>
            <div className="review-actions"><button className={`button button-outline ${selected.reviewStatus === 'rejected' ? 'button-rejected' : ''}`} disabled={busy} onClick={() => void mark('rejected')}><X size={15} /> Exclude</button><button className="button button-primary" disabled={busy} onClick={() => void mark('selected')}><UserRoundCheck size={16} /> Mark for review</button></div>
            <button className="button button-search" onClick={() => onOpenSearch(selected.id)}><Search size={16} /> Search SFace embeddings <ArrowRight size={16} /></button>
            <div className="watchlist-arm-row">
              <input id="watchlist-suspect-label" name="suspect_label" aria-label="Suspect label for live watchlist" value={suspectLabel} onChange={(e) => setSuspectLabel(e.target.value)} maxLength={40} placeholder="Suspect label" />
              <button type="button" className="button button-outline button-compact" disabled={arming || !suspectLabel.trim()} onClick={() => void armWatchlist()}>
                {arming ? <LoaderCircle size={13} className="spin" /> : <ShieldAlert size={14} />} Arm Live Watchlist
              </button>
            </div>
          </> : <div className="selected-empty"><ScanFace size={24} /><p>Candidate details and review actions appear here.</p></div>}
        </section>
        <section className="panel clip-player-panel"><SectionTitle title="Source footage" detail="Stored locally · use controls to inspect context" />{record ? <video ref={videoRef} src={`/api/clips/${record.clipId}/video`} controls muted playsInline preload="metadata" /> : <div className="video-skeleton"><LoaderCircle size={20} className="spin" /></div>}<div className="source-meta"><span><LockKeyhole size={13} /> LOCAL FILE</span><span>{record?.result?.windowStart !== undefined ? `${formatDuration(record.result.windowStart)}–${formatDuration(record.result.windowEnd || 0)}` : 'Transaction window'}</span></div></section>
        {record?.status === 'completed' && (
          <section ref={characteristicsRef} tabIndex={-1} aria-label="Physical characteristics" className="panel clip-player-panel">
            <SectionTitle title="Physical characteristics" detail="Footage assessment for the analyzed time window" />
            <p className="footage-assessment-summary">{record.result.sampledFrames ?? 0} frames sampled · {record.candidates.length} face candidates saved{record.result.trackingEngine ? ` · ${record.result.trackingEngine}` : ''}</p>
            <p className="footage-assessment-summary">{bestCandidate
              ? `Highest-ranked face crop at ${bestCandidate.timeLabel} · image quality ${Math.round(bestCandidate.score)}/100${bestCandidate.flags.length ? ` · ${bestCandidate.flags.join(', ')}` : ''}`
              : 'No face crop was found in this window. Open the source footage to inspect the scene.'}</p>
            <dl className="footage-assessment">
              <div><dt>Height</dt><dd>Needs a calibrated view with head and feet visible.</dd></div>
              <div><dt>Weight</dt><dd>Needs an independent measurement.</dd></div>
              <div><dt>Age</dt><dd>Needs a verified record or a validated age-range model with a clear face view.</dd></div>
              <div><dt>Gender</dt><dd>Needs self-reported or verified information.</dd></div>
            </dl>
            <button type="button" className="text-button frame-link" onClick={() => inspectSourceAt(assessmentTime)}><Video size={14} /> {bestCandidate ? 'Inspect the highest-ranked frame' : 'Inspect the start of the window'} <span>{formatDuration(assessmentTime)}</span></button>
          </section>
        )}
      </aside>
    </div>
    {record?.status === 'completed' && <section className="panel timeline-panel"><SectionTitle title="Transaction timeline" detail="Candidate frames within the selected time window" />
      <div className="timeline-track"><div className="timeline-range"><span>{formatDuration(record.result.windowStart || 0)}</span><div className="timeline-line"><i /><i /><i /></div><span>{formatDuration(record.result.windowEnd || 0)}</span></div><div className="transaction-marker" style={{ left: `${(() => {
        const ws = record.result.windowStart || 0;
        const we = Math.max(record.result.windowEnd ?? ws, ws + 0.001);
        const offset = record.transactionOffsetSeconds ?? ws;
        return Math.min(100, Math.max(0, ((offset - ws) / (we - ws)) * 100));
      })()}%` }}><span>{record.transactionTime}</span><i /></div>{record.candidates.map((candidate, index) => <button key={candidate.id} className="timeline-candidate" style={{ left: `${Math.min(96, Math.max(2, ((candidate.time - (record.result.windowStart || 0)) / Math.max((record.result.windowEnd || 1) - (record.result.windowStart || 0), 1)) * 100))}%` }} title={`${candidate.timeLabel} · score ${Math.round(candidate.score)}`} onClick={() => setSelectedId(candidate.id)}><i style={{ height: `${22 + candidate.score * 0.55}px` }} /><span>{index === 0 ? candidate.timeLabel : ''}</span></button>)}</div>
      <div className="timeline-legend"><span><i className="legend-transaction" />Transaction time</span><span><i className="legend-candidate" />Detected face frame</span><span>{record.result.sampledFrames || 0} frames sampled</span></div>
    </section>}
    <div className="review-disclaimer"><Shield size={15} /><span>Human verification required. Visual similarity and quality scores are aids for authorised review, not identity verification or guilt findings.</span></div>
    {showPrivacyModal && selected && createPortal(
      <div className="privacy-modal-backdrop" role="dialog" aria-modal="true" aria-label="Bystander-redacted privacy frame">
        <div className="privacy-modal">
          <div className="section-title">
            <div><h2>Privacy-Preserving Bystander Redaction</h2><p>Target candidate stays visible; non-target bystander faces are Gaussian-blurred with SHA-256 provenance.</p></div>
            <button className="icon-button" aria-label="Close privacy frame" onClick={() => setShowPrivacyModal(false)}><X size={18} /></button>
          </div>
          <img src={selected.redactedFrameUrl} alt="Bystander-redacted evidence frame" />
          <div className="form-row">
            <span className="local-chip"><ShieldCheck size={14} /> DPDP PRIVACY EXPORT</span>
            <a className="button button-primary button-compact" href={selected.redactedFrameUrl} download={`redacted-${selected.id.slice(0, 10)}.jpg`}>
              <Download size={14} /> Download Redacted Frame
            </a>
          </div>
        </div>
      </div>,
      document.body
    )}
  </>;
}

function QualityBars({ metrics }: { metrics: Candidate['metrics'] }) {
  const rows: [string, number][] = [
    ['Sharpness', metrics.sharpness],
    ['Illumination', metrics.illumination],
    ['Pose', metrics.pose],
    ['Face size', metrics.faceSize],
  ];
  if (typeof metrics.occlusionFree === 'number') {
    rows.push(['Clear face', metrics.occlusionFree]);
  }
  return <div className="quality-breakdown"><div className="quality-heading"><strong>Frame quality signals</strong><span>0–100</span></div>{rows.map(([label, value]) => <div className="quality-row" key={label}><span>{label}</span><div><i style={{ width: `${value}%` }} /></div><strong>{value}</strong></div>)}</div>;
}

function SearchWorkspace({ analyses, candidateId, onCandidateChange, onReview }: {
  analyses: Analysis[]; candidateId: string; onCandidateChange: (id: string) => void; onReview: (id: string) => void;
}) {
  const [matches, setMatches] = useState<(Candidate & { similarity: number; filename: string })[]>([]);
  const [notice, setNotice] = useState('');
  const [threshold, setThreshold] = useState(52);
  const [busy, setBusy] = useState(false);
  const candidates = useMemo(() => analyses.flatMap((analysis) => analysis.candidates.map((candidate) => ({ ...candidate, clipName: analysis.clipName }))), [analyses]);
  const selected = candidates.find((candidate) => candidate.id === candidateId);

  useEffect(() => { setMatches([]); setNotice(''); }, [candidateId]);

  const search = async () => {
    if (!candidateId) return;
    setBusy(true);
    try { const result = await api.search(candidateId, threshold / 100); setMatches(result.matches); setNotice(result.notice); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Search failed.'); }
    finally { setBusy(false); }
  };

  return <div className="search-layout">
    <section className="panel search-source-panel"><SectionTitle title="Choose a face frame" detail="Select a reviewed candidate as the SFace embedding reference." />
      <label className="field-label" htmlFor="candidate-source">Reference candidate</label>
      <div className="select-wrap"><ScanFace size={17} /><select id="candidate-source" name="candidate_id" value={candidateId} onChange={(event) => onCandidateChange(event.target.value)}><option value="">Select candidate…</option>{candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.clipName} · {candidate.timeLabel} · Track {String(candidate.trackId).padStart(2, '0')} · score {Math.round(candidate.score)}</option>)}</select><ChevronDown size={16} /></div>
      {selected && <div className="search-reference"><img src={selected.imageUrl} alt="Search reference candidate" /><div><strong>{selected.clipName}</strong><span>{selected.timeLabel} · Track {selected.trackId}</span><b>Frame quality {Math.round(selected.score)}/100</b></div></div>}
      <div className="threshold-row">
        <label htmlFor="similarity-threshold">Minimum cosine similarity</label>
        <strong className="mono-data">{threshold}%</strong>
      </div>
      <div className="threshold-row">
        <input id="similarity-threshold" name="threshold" type="range" min={35} max={90} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
      </div>
      <div className="search-method"><Fingerprint size={18} /><div><strong>Local SFace 128-D embedding search</strong><span>Compares deep facial embeddings from uploaded workspace clips only. No Aadhaar or external criminal databases.</span></div></div>
      <button className="button button-primary search-submit" disabled={!candidateId || busy} onClick={() => void search()}>{busy ? <LoaderCircle size={17} className="spin" /> : <Search size={17} />}{busy ? 'Searching embeddings…' : 'Search other clips'}<ArrowRight size={17} /></button>
    </section>

    <section className="panel search-results-panel"><SectionTitle title="Similar candidates" detail={matches.length ? `${matches.length} results from other clips` : 'Search results appear here'} action={matches.length > 0 ? <span className="sorted-indicator">BEST MATCH FIRST</span> : undefined} />
      {notice && <div className="search-notice"><AlertCircle size={15} />{notice}</div>}
      {matches.length ? <div className="match-list">{matches.map((match) => <article className="match-row" key={match.id}><img src={match.imageUrl} alt="Similar candidate frame" /><div className="match-main"><strong>{match.filename}</strong><span>{match.timeLabel} · Track {match.trackId} · Frame quality {Math.round(match.score)}</span><div className="match-flags">{match.flags.map((flag) => <small key={flag}>{flag}</small>)}</div></div><div className="similarity-score"><strong>{Math.round(match.similarity)}%</strong><span>embedding match</span></div><button className="button button-outline button-compact" onClick={() => onReview(match.analysisId)}>Review clip <ChevronRight size={15} /></button></article>)}</div> : <div className="search-empty"><div className="search-empty-icon"><Search size={24} /></div><h3>{busy ? 'Searching local clips' : candidateId ? 'No matches found' : 'Choose a reference candidate'}</h3><p>{busy ? 'Comparing 128-D embeddings across other clips in this local workspace.' : candidateId ? 'No candidate crossed the similarity threshold. Lower the threshold or test another clip.' : 'Run an analysis and choose a candidate frame to compare it across other uploaded clips.'}</p></div>}
    </section>
  </div>;
}

function Reports({ data, analyses, events }: { data: ReportsData | null; analyses: Analysis[]; events: EventItem[] }) {
  const completed = data?.analyses.completed || 0;
  const failed = data?.analyses.failed || 0;
  const reviewed = data?.reviews.selected || 0;
  const rejected = data?.reviews.rejected || 0;
  const weeks = analyses.slice(0, 6).reverse();
  const flagEntries = Object.entries(data?.flags || {}).sort((a, b) => b[1] - a[1]);
  const streamEntries = Object.entries(data?.streams || {});

  return <>
    <div className="report-summary"><Stat label="Analyses completed" value={completed} detail="Local processing jobs" icon={<BadgeCheck size={19} />} tone="teal" /><Stat label="Candidates marked" value={reviewed} detail="For further human review" icon={<UserRoundCheck size={19} />} tone="amber" /><Stat label="Average frame score" value={`${data?.quality.average ?? 0}`} detail="Across extracted candidates" icon={<Gauge size={19} />} /><Stat label="Processing issues" value={failed} detail="Jobs needing attention" icon={<AlertCircle size={19} />} tone={failed ? 'red' : 'navy'} /></div>
    <div className="reports-grid">
      <section className="panel report-panel"><SectionTitle title="Review outcomes" detail="Candidate status distribution" />
        {[['Marked for review', reviewed, 'bar-teal'], ['Excluded by reviewer', rejected, 'bar-red'], ['Not yet reviewed', data?.reviews.unreviewed || 0, 'bar-amber']].map(([label, value, color]) => <div className="report-bar-row" key={String(label)}><div><span>{label}</span><strong>{value}</strong></div><div className="report-bar-track"><i className={String(color)} style={{ width: `${Math.max(value ? 4 : 0, (Number(value) / Math.max(reviewed + rejected + (data?.reviews.unreviewed || 0), 1)) * 100)}%` }} /></div></div>)}
        <div className="report-footnote"><ShieldCheck size={15} /> Review labels are operator decisions, not automated verdicts.</div>
      </section>
      <section className="panel report-panel"><SectionTitle title="Recent analysis windows" detail="Transaction-linked review activity" />
        {weeks.length ? <div className="mini-timeline">{weeks.map((item) => <div className="mini-time-item" key={item.id}><div className="mini-time-bar"><i style={{ height: `${Math.max(10, (item.result?.candidateCount || 1) * 18)}px` }} className={item.status === 'failed' ? 'bar-fill-red' : 'bar-fill-navy'} /></div><span>{new Date(item.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span><small>{item.result?.candidateCount ?? '—'} frames</small></div>)}</div> : <EmptyLine icon={<BarChart3 size={18} />} title="No analysis history" detail="Reports build from completed local investigations." />}
        <div className="chart-axis"><span>Older</span><span>Each bar = one investigation</span><span>Recent</span></div>
      </section>
    </div>
    <div className="reports-grid">
      <section className="panel report-panel">
        <SectionTitle title="Reliability &amp; occlusion flags" detail="Masks, caps, helmets, and lighting flags observed" />
        {flagEntries.length ? flagEntries.slice(0, 6).map(([flag, count]) => (
          <div className="report-bar-row" key={flag}><div><span>{flag}</span><strong>{count}</strong></div><div className="report-bar-track"><i className="bar-amber" style={{ width: `${Math.min(100, count * 14)}%` }} /></div></div>
        )) : <EmptyLine icon={<AlertTriangle size={18} />} title="No reliability flags logged" detail="Occlusion and lighting flags appear after candidate extraction." />}
      </section>
      <section className="panel report-panel">
        <SectionTitle title="4-Stream surveillance telemetry" detail="Person &amp; face detection events per CCTV camera" />
        {streamEntries.length ? streamEntries.map(([camId, info]) => (
          <div className="report-bar-row" key={camId}><div><span>{camId}</span><strong>{info.detections} person hits ({info.events} logs)</strong></div><div className="report-bar-track"><i className="bar-teal" style={{ width: `${Math.min(100, Math.max(8, info.events * 10))}%` }} /></div></div>
        )) : <EmptyLine icon={<Radio size={18} />} title="No live stream telemetry yet" detail="Run the 4-Stream Surveillance Wall to gather camera statistics." />}
      </section>
    </div>
    <section className="panel report-events"><SectionTitle title="Event register" detail="Processing and surveillance alert events with timestamps" />{events.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>EVENT</th><th>DETAIL</th><th>SEVERITY</th><th>TIME</th></tr></thead><tbody>{events.slice(0, 20).map((event) => <tr key={event.id}><td><strong>{event.kind}</strong></td><td>{event.message}</td><td><span className={`severity severity-${event.severity}`}>{event.severity}</span></td><td className="mono-data">{new Date(event.occurredAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</td></tr>)}</tbody></table></div> : <EmptyLine icon={<Activity size={18} />} title="No system events yet" detail="Processing events are recorded here once a clip is analysed." />}</section>
  </>;
}

function Audit({ items, events, integrity }: { items: AuditItem[]; events: EventItem[]; integrity: AuditIntegrity | null }) {
  const [filter, setFilter] = useState('all');
  const combined = useMemo(() => [
    ...items.map((item) => ({ id: item.id, kind: item.action, message: item.description ?? item.note, time: item.occurredAt, source: 'Audit entry', severity: '', actor: item.actorId, subject: item.subjectId })),
    ...events.map((item) => ({ id: item.id, kind: item.kind, message: item.message, time: item.occurredAt, source: 'System event', severity: item.severity, actor: null, subject: '' })),
  ].sort((a, b) => b.time.localeCompare(a.time)), [items, events]);
  const visible = filter === 'all' ? combined : combined.filter((item) => item.source === filter);
  return <section className="panel audit-panel">
    <SectionTitle
      title="Audit log"
      detail="Local record of file handling, analysis, surveillance, and candidate review actions"
      action={
        <div className="page-actions">
          <a className="button button-outline button-compact" href="/api/audit/export?format=csv" download><Download size={14} /> CSV</a>
          <a className="button button-outline button-compact" href="/api/audit/export?format=json" download><FileCode2 size={14} /> Signed JSON</a>
          <div className="audit-filters"><button className={filter === 'all' ? 'filter-active' : ''} onClick={() => setFilter('all')}>All</button><button className={filter === 'Audit entry' ? 'filter-active' : ''} onClick={() => setFilter('Audit entry')}>Audit entries</button><button className={filter === 'System event' ? 'filter-active' : ''} onClick={() => setFilter('System event')}>System events</button></div>
        </div>
      }
    />
    <div className={`audit-chain ${integrity?.verified ? 'audit-chain-ok' : integrity ? 'audit-chain-failed' : ''}`} role="status">
      {integrity?.verified ? <BadgeCheck size={17} /> : <ShieldCheck size={17} />}
      <strong>{integrity ? (integrity.verified ? 'AUDIT CHAIN VERIFIED' : 'AUDIT CHAIN CHECK FAILED') : 'CHECKING AUDIT CHAIN'}</strong>
      {integrity && <span>{integrity.entriesChecked} entries checked</span>}
      {!integrity?.verified && integrity?.reason && <span>{integrity.reason}</span>}
    </div>
    {visible.length ? <div className="table-scroll"><table className="data-table audit-table"><thead><tr><th>TIME</th><th>ACTION</th><th>DETAIL</th><th>SUBJECT / ACCOUNT ID</th><th>TYPE</th><th>SEVERITY</th></tr></thead><tbody>{visible.map((item) => <tr key={`${item.source}-${item.id}`}><td className="mono-data">{new Date(item.time).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' })}</td><td><strong>{item.kind}</strong></td><td>{item.message}</td><td>{item.subject || '—'}{item.actor && <><br />Account: {item.actor}</>}</td><td><span className="source-label">{item.source}</span></td><td>{item.severity ? <span className={`severity severity-${item.severity}`}>{item.severity}</span> : '—'}</td></tr>)}</tbody></table></div> : <EmptyLine icon={<FileClock size={18} />} title="No audit entries" detail="Upload, analysis and review actions appear here." />}
    <div className="audit-footnote"><LockKeyhole size={15} /> Hash-linked audit records reveal accidental or partial changes; privileged database rewrites require external signed checkpoints to detect.</div>
  </section>;
}

export default App;
