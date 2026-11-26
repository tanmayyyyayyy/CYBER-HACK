import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, BadgeCheck, BarChart3, Bell,
  Camera, Check, CheckCircle2, ChevronDown, ChevronRight, Clock3, Crosshair,
  Database, Download, Eye, FileClock, FileSearch, FileVideo2, Fingerprint, LogOut,
  FolderOpen, Gauge, HardDrive, History, House, LoaderCircle,
  LockKeyhole, Menu, Play, Plus, RefreshCw, Search, ScanFace,
  Shield, ShieldCheck, SlidersHorizontal, Trash2, Upload, UserRoundCheck,
  UsersRound, X,
} from 'lucide-react';
import { api, Analysis, AuditIntegrity, AuditItem, AuthUser, CameraSlot, Candidate, Clip, DatabaseBackup, EventItem, formatBytes, formatDuration, Health, SecurityOverview } from './api';

type Page = 'desk' | 'library' | 'search' | 'reports' | 'audit' | 'review' | 'accounts' | 'security';
type Toast = { kind: 'success' | 'error'; message: string } | null;

const pageCopy: Record<Page, { title: string; subtitle: string }> = {
  desk: { title: 'Case desk', subtitle: 'Review ATM footage around a transaction timestamp.' },
  library: { title: 'Video library', subtitle: 'Four local evidence channels. Uploaded clips stay on this machine.' },
  search: { title: 'Cross-clip search', subtitle: 'Find visually similar face candidates in other uploaded clips.' },
  reports: { title: 'Reports & analytics', subtitle: 'A traceable view of local case work and review progress.' },
  audit: { title: 'Audit trail', subtitle: 'Operator actions and analysis events recorded on this device.' },
  review: { title: 'Evidence review', subtitle: 'Compare candidate frames and record a human review decision.' },
  accounts: { title: 'Access control', subtitle: 'Approve local investigator accounts and revoke access.' },
  security: { title: 'Security center', subtitle: 'Database health, evidence integrity and local threat controls.' },
};

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    void Promise.allSettled([api.authBootstrap(), api.authMe()]).then(([bootstrap, session]) => {
      if (!alive) return;
      if (bootstrap.status === 'fulfilled') setSetupRequired(bootstrap.value.needsAdministrator);
      if (session.status === 'fulfilled') { setUser(session.value.user); setSetupRequired(false); }
      setAuthLoading(false);
    });
    const expire = () => { setUser(null); setSetupRequired(false); };
    window.addEventListener('drishti:session-expired', expire);
    return () => { alive = false; window.removeEventListener('drishti:session-expired', expire); };
  }, []);

  const signOut = async () => {
    try { await api.authLogout(); } finally { setUser(null); }
  };
  if (authLoading) return <div className="auth-loading"><div className="brand-emblem"><ScanFace size={22} /></div><strong>DRISHTI</strong><span>Checking local access…</span></div>;
  if (!user) return <AuthPortal setupRequired={setupRequired} onAuthenticated={(account) => { setSetupRequired(false); setUser(account); }} />;
  return <Workspace user={user} onSignOut={signOut} />;
}

function Workspace({ user, onSignOut }: { user: AuthUser; onSignOut: () => Promise<void> }) {
  const [page, setPage] = useState<Page>('desk');
  const [clips, setClips] = useState<Clip[]>([]);
  const [cameras, setCameras] = useState<CameraSlot[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [auditIntegrity, setAuditIntegrity] = useState<AuditIntegrity | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [reportData, setReportData] = useState<Awaited<ReturnType<typeof api.reports>> | null>(null);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState('');
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [toast, setToast] = useState<Toast>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [smallNavOpen, setSmallNavOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadCameraId, setUploadCameraId] = useState('ATM-01');

  const refresh = useCallback(async (quiet = true) => {
    if (!quiet) setRefreshing(true);
    const [healthResult, clipsResult, camerasResult, analysesResult, eventsResult, auditResult, auditIntegrityResult, reportsResult] = await Promise.allSettled([
      api.health(), api.clips(), api.cameras(), api.analyses(), api.events(), api.audit(), api.auditIntegrity(), api.reports(),
    ]);
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
    if (clipsResult.status === 'fulfilled') setClips(clipsResult.value);
    if (camerasResult.status === 'fulfilled') setCameras(camerasResult.value);
    if (analysesResult.status === 'fulfilled') setAnalyses(analysesResult.value);
    if (eventsResult.status === 'fulfilled') setEvents(eventsResult.value);
    if (auditResult.status === 'fulfilled') setAudit(auditResult.value);
    if (auditIntegrityResult.status === 'fulfilled') setAuditIntegrity(auditIntegrityResult.value);
    if (reportsResult.status === 'fulfilled') setReportData(reportsResult.value);
    if ([healthResult, clipsResult, camerasResult, analysesResult].some((result) => result.status === 'rejected')) {
      if (!quiet) setToast({ kind: 'error', message: 'Could not reach the local API. Start the local server and retry.' });
    }
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void refresh(false);
    const timer = window.setInterval(() => void refresh(), 8000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4200);
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

  const requestUpload = (cameraId: string) => {
    setUploadCameraId(cameraId);
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
      const clip = await api.upload(file, uploadCameraId);
      setToast({ kind: 'success', message: `${clip.filename} added to ${uploadCameraId}.` });
      await refresh();
    } catch (error) {
      setToast({ kind: 'error', message: error instanceof Error ? error.message : 'Upload failed.' });
    }
  };

  const selectedAnalysis = analyses.find((item) => item.id === selectedAnalysisId);
  const pageMeta = pageCopy[page];

  return (
    <div className="app-shell">
      <input ref={fileInput} className="sr-only" type="file" accept="video/*,.mpeg,.mpg" onChange={handleUpload} />
      <aside className={`side-rail ${smallNavOpen ? 'side-rail-open' : ''}`}>
        <div className="brand-lockup">
          <div className="brand-emblem" aria-hidden="true"><ScanFace size={21} strokeWidth={1.8} /></div>
          <div><strong>DRISHTI</strong><span>FORENSIC REVIEW</span></div>
          <button className="icon-button rail-close" aria-label="Close navigation" onClick={() => setSmallNavOpen(false)}><X size={17} /></button>
        </div>

        <div className="rail-divider" />
        <p className="rail-label">WORKSPACE</p>
        <nav className="main-nav" aria-label="Main navigation">
          <NavItem active={page === 'desk' || page === 'review'} label="Case desk" icon={<House size={17} />} onClick={() => { setPage('desk'); setSmallNavOpen(false); }} />
          <NavItem active={page === 'library'} label="Video library" icon={<Camera size={17} />} count={clips.length || undefined} onClick={() => { setPage('library'); setSmallNavOpen(false); }} />
          <NavItem active={page === 'search'} label="Cross-clip search" icon={<ScanFace size={17} />} onClick={() => openSearch()} />
          <NavItem active={page === 'reports'} label="Reports & analytics" icon={<BarChart3 size={17} />} onClick={() => { setPage('reports'); setSmallNavOpen(false); }} />
          <NavItem active={page === 'audit'} label="Audit trail" icon={<FileClock size={17} />} onClick={() => { setPage('audit'); setSmallNavOpen(false); }} />
          {user.role === 'administrator' && <NavItem active={page === 'accounts'} label="Access control" icon={<UsersRound size={17} />} onClick={() => { setPage('accounts'); setSmallNavOpen(false); }} />}
          {user.role === 'administrator' && <NavItem active={page === 'security'} label="Security center" icon={<ShieldCheck size={17} />} onClick={() => { setPage('security'); setSmallNavOpen(false); }} />}
        </nav>

        <div className="rail-bottom">
          <div className="rail-divider" />
          <div className="storage-card">
            <div className="storage-icon"><HardDrive size={16} /></div>
            <div><strong>Local evidence vault</strong><span>Files stay on this device</span></div>
            <span className="live-dot" title="Local mode" />
          </div>
          <div className="prototype-note"><Shield size={13} /> Local product pilot · Not an official Rajasthan Police system</div>
          <div className="profile-row">
            <div className="profile-avatar">{user.displayName.slice(0, 2).toUpperCase()}</div>
            <div className="profile-copy"><strong>{user.displayName}</strong><span>{user.role === 'administrator' ? 'Administrator' : 'Investigator'}</span></div>
            <button className="icon-button muted-icon" aria-label="Sign out" title="Sign out" onClick={() => void onSignOut()}><LogOut size={17} /></button>
          </div>
        </div>
      </aside>

      {smallNavOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setSmallNavOpen(false)} />}

      <main className="main-column">
        <header className="topbar">
          <button className="icon-button menu-toggle" aria-label="Open navigation" onClick={() => setSmallNavOpen(true)}><Menu size={20} /></button>
          <div className="breadcrumbs"><span>DRISHTI</span><ChevronRight size={14} /><strong>{pageMeta.title}</strong></div>
          <div className="topbar-right">
            <div className="local-status"><span className={`status-orb ${health ? 'status-ready' : 'status-loading'}`} /><span>{health ? 'LOCAL MODE' : 'CONNECTING'}</span></div>
            <span className="topbar-divider" />
            <button className="icon-button notification-button" aria-label="Recent events" onClick={() => setPage('audit')}><Bell size={18} />{events.some((item) => item.severity === 'warning') && <i />}</button>
            <div className="topbar-clock"><span>JAIPUR, IN</span><strong>{new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })}</strong></div>
          </div>
        </header>

        <div className="page-wrap">
          <div className="page-heading">
            <div><h1>{pageMeta.title}</h1><p>{pageMeta.subtitle}</p></div>
            <div className="page-actions">
              <span className="local-chip"><LockKeyhole size={13} /> LOCAL ONLY</span>
              <button className="button button-outline button-compact" onClick={() => void refresh(false)} disabled={refreshing}>
                <RefreshCw size={15} className={refreshing ? 'spin' : ''} /> Refresh
              </button>
            </div>
          </div>

          {page === 'desk' && <CaseDesk clips={clips} cameras={cameras} analyses={analyses} health={health} events={events} onUpload={requestUpload} onReview={openReview} onToast={setToast} />}
          {page === 'library' && <Library clips={clips} cameras={cameras} onUpload={requestUpload} onDelete={async (clip) => {
            try { await api.deleteClip(clip.id); setToast({ kind: 'success', message: `${clip.filename} removed from local storage.` }); await refresh(); }
            catch (error) { setToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not remove clip.' }); }
          }} />}
          {page === 'review' && <Review analysisId={selectedAnalysisId} analysisSummary={selectedAnalysis} onOpenSearch={openSearch} onToast={setToast} onRefresh={() => refresh()} />}
          {page === 'search' && <SearchWorkspace analyses={analyses} candidateId={selectedCandidateId} onCandidateChange={setSelectedCandidateId} onReview={openReview} />}
          {page === 'reports' && <Reports data={reportData} analyses={analyses} events={events} />}
          {page === 'audit' && <Audit items={audit} events={events} integrity={auditIntegrity} />}
          {page === 'accounts' && user.role === 'administrator' && <AccessControl currentUser={user} onToast={setToast} />}
          {page === 'security' && user.role === 'administrator' && <SecurityCenter onToast={setToast} />}
        </div>
      </main>

      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span>{toast.kind === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}</span><p>{toast.message}</p><button aria-label="Dismiss message" onClick={() => setToast(null)}><X size={15} /></button></div>}
    </div>
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
      <div className="auth-brand"><div className="brand-emblem"><ScanFace size={22} /></div><div><strong>DRISHTI</strong><span>FORENSIC REVIEW</span></div></div>
      <div className="auth-art-copy"><span className="auth-kicker"><ShieldCheck size={14} /> LOCAL EVIDENCE WORKSPACE</span><h1>Careful review.<br /><em>Clear evidence.</em></h1><p>Transaction-led ATM footage review for authorised investigators.</p></div>
      <div className="auth-art-foot"><LockKeyhole size={14} /> Evidence and accounts stay on this device.</div>
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
          {mode === 'signup' && <label>Full name<input autoComplete="name" required minLength={2} maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="Investigator name" /></label>}
          <label>Work email<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@department.gov.in" /></label>
          <label>Passphrase<input type="password" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={mode === 'signup' ? 12 : 1} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === 'signup' ? 'At least 12 characters' : 'Your passphrase'} /></label>
          {mode === 'signup' && <div className="auth-security-note"><Shield size={15} /> Passphrases are stored as salted scrypt hashes. No password recovery service is configured.</div>}
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
  const [working, setWorking] = useState<'check' | 'backup' | ''>('');
  const [backupPassphrase, setBackupPassphrase] = useState('');
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

  const dbHealthy = overview?.database.integrity === 'ok' && overview.database.foreignKeyViolations === 0;
  const permissionsHealthy = Boolean(overview?.database.directoryPermissions.restricted && overview.database.filePermissions.restricted);
  const auditHealthy = Boolean(overview?.audit.verified);
  const formatStamp = (value: string) => new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });

  return <div className="security-workspace">
    <div className="security-banner"><div className="security-banner-icon"><ShieldCheck size={22} /></div><div><strong>Defence in depth for local evidence</strong><span>Checks are explicit and auditable. Host encryption remains an administrator responsibility.</span></div><button className="button button-outline button-compact" onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /> Recheck</button></div>
    <div className="security-cards">
      <SecurityCard icon={<Database size={17} />} title="SQLite health" value={loading ? 'Checking…' : dbHealthy ? 'Healthy' : 'Review required'} detail={overview ? `${overview.database.integrity} · ${overview.database.foreignKeyViolations} foreign-key issues · ${formatBytes(overview.database.sizeBytes)}` : 'Running integrity checks'} ok={dbHealthy} />
      <SecurityCard icon={<Fingerprint size={17} />} title="Audit chain" value={loading ? 'Checking…' : auditHealthy ? 'Verified' : 'Integrity alert'} detail={overview ? `${overview.audit.entriesChecked} linked entries checked` : 'Verifying linked records'} ok={auditHealthy} />
      <SecurityCard icon={<HardDrive size={17} />} title="Local file permissions" value={loading ? 'Checking…' : permissionsHealthy ? 'Restricted' : 'Review permissions'} detail={overview ? `Data folder ${overview.database.directoryPermissions.mode} · DB ${overview.database.filePermissions.mode}` : 'Checking private storage modes'} ok={permissionsHealthy} />
      <SecurityCard icon={<UsersRound size={17} />} title="Account signals" value={overview ? `${overview.accounts.pending} pending approval` : 'Checking…'} detail={overview ? `${overview.accounts.active} active · ${overview.accounts.failedSignins24h} denied sign-ins in 24h` : 'Loading local account status'} ok={Boolean(overview && overview.accounts.failedSignins24h === 0 && overview.accounts.pending === 0)} />
      <SecurityCard icon={<LockKeyhole size={17} />} title="Host disk encryption" value="Verify on device" detail="Enable FileVault, BitLocker or LUKS for the volume storing local evidence." ok={false} />
      <SecurityCard icon={<Shield size={17} />} title="Network exposure" value="Loopback only" detail="The app binds to 127.0.0.1. Keep shared-network proxies disabled until a security review." ok />
    </div>

    <div className="security-tools-grid">
      <section className="panel security-tool-panel"><SectionTitle title="Evidence integrity sweep" detail="Rehash original recordings and analysis copies against ingest fingerprints." />
        <div className="security-tool-body"><div className="security-tool-icon"><Fingerprint size={19} /></div><div className="security-tool-copy"><strong>{overview?.evidence.clipCount ?? 0} clip(s) in local vault</strong><span>{overview?.evidence.lastFullCheck ? `Last full check ${formatStamp(overview.evidence.lastFullCheck.checkedAt)} · ${overview.evidence.lastFullCheck.mismatchCount} mismatch(es)` : 'No full evidence verification has been run yet.'}</span></div></div>
        <button className="button button-primary" onClick={() => void verifyEvidence()} disabled={loading || working !== '' || !overview?.evidence.clipCount}>{working === 'check' ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />} Run full evidence check</button>
        {evidenceResult && <div className={`security-result ${evidenceResult.mismatches.length ? 'security-result-error' : ''}`} role="status"><strong>{evidenceResult.verified}/{evidenceResult.checked} files verified</strong><span>{evidenceResult.notice}</span>{evidenceResult.mismatches.map((item) => <small key={item.clipId}>{item.filename} · source {item.sourceMatches ? 'OK' : 'MISMATCH'} · analysis {item.analysisMatches ? 'OK' : 'MISMATCH'}</small>)}</div>}
      </section>

      <section className="panel security-tool-panel"><SectionTitle title="Encrypted database snapshot" detail="Make a portable, authenticated SQLite metadata backup." />
        <form className="security-backup-form" onSubmit={(event) => void createBackup(event)}><label>Backup passphrase<input type="password" autoComplete="new-password" minLength={16} maxLength={256} required value={backupPassphrase} onChange={(event) => setBackupPassphrase(event.target.value)} placeholder="Use 16+ characters; keep it safe" /></label><button className="button button-primary" type="submit" disabled={working !== '' || backupPassphrase.length < 16}>{working === 'backup' ? <LoaderCircle size={15} className="spin" /> : <LockKeyhole size={15} />} Create encrypted snapshot</button></form>
        <p className="security-warning"><AlertCircle size={14} /> AES-256-GCM encrypted. The passphrase is not saved. This snapshot contains database records only; use a separately protected filesystem backup for video and candidate image files.</p>
        {backups.length > 0 && <div className="backup-list"><strong>Recent snapshots</strong>{backups.slice(0, 5).map((backup) => <div className="backup-row" key={backup.id}><div><span>{formatStamp(backup.createdAt)}</span><code>{backup.sha256.slice(0, 20)}…</code></div><a className="button button-outline button-compact" href={`/api/security/database-backups/${backup.id}`}><Download size={14} /> Download</a></div>)}</div>}
        {!backups.length && <div className="security-empty">No encrypted database snapshot yet.</div>}
      </section>
    </div>
    <div className="security-disclaimer"><LockKeyhole size={14} /> This local security layer is not a certified police deployment. Keep evidence on an encrypted host volume and maintain an independently controlled copy of important audit checkpoints.</div>
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

function CaseDesk({ clips, cameras, analyses, health, events, onUpload, onReview, onToast }: {
  clips: Clip[]; cameras: CameraSlot[]; analyses: Analysis[]; health: Health | null;
  events: EventItem[]; onUpload: (cameraId: string) => void; onReview: (id: string) => void; onToast: (toast: Toast) => void;
}) {
  const [clipId, setClipId] = useState('');
  const [mode, setMode] = useState<'clip' | 'absolute'>('clip');
  const [time, setTime] = useState('00:00:04');
  const [clipStart, setClipStart] = useState('');
  const [reference, setReference] = useState('');
  const [windowSeconds, setWindowSeconds] = useState(30);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { if (!clips.some((clip) => clip.id === clipId)) setClipId(clips[0]?.id || ''); }, [clips, clipId]);

  const createCase = async (event: FormEvent) => {
    event.preventDefault();
    if (!clipId) { onToast({ kind: 'error', message: 'Upload an ATM clip before starting analysis.' }); return; }
    if (mode === 'absolute' && !clipStart) { onToast({ kind: 'error', message: 'Enter the CCTV clip start timestamp to link the bank transaction.' }); return; }
    setSubmitting(true);
    try {
      const result = await api.analyze({
        clip_id: clipId,
        transaction_time: mode === 'clip' ? time : new Date(time).toISOString(),
        time_mode: mode,
        clip_start_time: mode === 'absolute' ? new Date(clipStart).toISOString() : '',
        transaction_ref: reference,
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
        <Stat label="Footage clips" value={clips.length} detail="In local evidence vault" icon={<FileVideo2 size={18} />} />
        <Stat label="Completed reviews" value={analyses.filter((item) => item.status === 'completed').length} detail={`${analyses.filter((item) => item.status === 'running').length} currently processing`} icon={<FileSearch size={18} />} tone="teal" />
        <Stat label="Person tracks" value={peopleCount} detail="Across completed clips" icon={<UsersRound size={18} />} tone="amber" />
        <Stat label="Face candidates" value={reviewedCount} detail="Require investigator review" icon={<ScanFace size={18} />} tone="red" />
      </div>

      <div className="desk-grid">
        <section className="panel intake-panel">
          <SectionTitle title="Start an investigation" detail="Link one clip to the transaction time." />
          <form className="intake-form" onSubmit={createCase}>
            <label className="field-label" htmlFor="clip-select">ATM footage</label>
            <div className="select-wrap"><FileVideo2 size={16} /><select id="clip-select" value={clipId} onChange={(event) => setClipId(event.target.value)} disabled={!clips.length}>
              {clips.length ? clips.map((clip) => <option key={clip.id} value={clip.id}>{clip.cameraId} · {clip.filename}</option>) : <option value="">No clips uploaded</option>}
            </select><ChevronDown size={15} /></div>
            {!clips.length && <button type="button" className="inline-link" onClick={() => onUpload('ATM-01')}><Upload size={14} /> Upload an ATM clip</button>}

            <div className="form-row between-row">
              <label className="field-label" htmlFor="transaction-time">Transaction time</label>
              <div className="segmented-control" aria-label="Time format">
                <button type="button" className={mode === 'clip' ? 'segment-active' : ''} onClick={() => { setMode('clip'); setTime('00:00:04'); }}>Clip time</button>
                <button type="button" className={mode === 'absolute' ? 'segment-active' : ''} onClick={() => { setMode('absolute'); setTime(''); }}>Bank time</button>
              </div>
            </div>
            {mode === 'clip' ? <div className="time-entry"><Clock3 size={16} /><input id="transaction-time" type="text" inputMode="numeric" pattern="\d{2,3}:\d{2}:\d{2}" placeholder="HH:MM:SS" value={time} onChange={(event) => setTime(event.target.value)} required /><span>HH:MM:SS</span></div> : <div className="time-entry"><Clock3 size={16} /><input id="transaction-time" type="datetime-local" value={time} onChange={(event) => setTime(event.target.value)} required /></div>}
            {mode === 'absolute' && <label className="field-group"><span className="field-label">CCTV clip start timestamp</span><input type="datetime-local" value={clipStart} onChange={(event) => setClipStart(event.target.value)} required /></label>}

            <div className="form-grid-two">
              <label className="field-group"><span className="field-label">Transaction reference <i>optional</i></span><input type="text" maxLength={40} placeholder="e.g. TXN-ATM-2481" value={reference} onChange={(event) => setReference(event.target.value)} /></label>
              <label className="field-group"><span className="field-label">Search window</span><select value={windowSeconds} onChange={(event) => setWindowSeconds(Number(event.target.value))}><option value={15}>±15 seconds</option><option value={30}>±30 seconds</option><option value={60}>±60 seconds</option><option value={120}>±2 minutes</option><option value={300}>±5 minutes</option></select></label>
            </div>
            <div className="form-callout"><ShieldCheck size={16} /><span>Frame ranking supports review. It does not identify a person or establish guilt.</span></div>
            <button className="button button-primary intake-submit" disabled={submitting || !clips.length || !health} type="submit">{submitting ? <LoaderCircle size={16} className="spin" /> : <ScanFace size={16} />}{submitting ? 'Starting local analysis…' : 'Find best face frames'}<ArrowRight size={16} /></button>
          </form>
        </section>

        <section className="panel camera-panel">
          <SectionTitle title="Four camera views" detail="Uploaded recordings · local playback only" action={<span className="recorded-chip"><span /> {clips.length} CLIPS</span>} />
          <CameraWall cameras={cameras} onUpload={onUpload} compact />
          <div className="camera-footnote"><LockKeyhole size={13} /> No live bank CCTV connection · no cloud stream proxy</div>
        </section>
      </div>

      <div className="lower-grid">
        <section className="panel recent-panel">
          <SectionTitle title="Recent investigations" detail="Latest analysis activity" action={<button className="text-button" onClick={() => onReview(analyses[0]?.id || '')} disabled={!analyses.length}>View all <ArrowRight size={14} /></button>} />
          {analyses.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>CLIP / CAMERA</th><th>TRANSACTION TIME</th><th>RESULT</th><th>STATUS</th><th /></tr></thead><tbody>
            {analyses.slice(0, 5).map((item) => <tr key={item.id} onClick={() => onReview(item.id)} className="clickable-row"><td><strong>{item.clipName}</strong><span>{clips.find((clip) => clip.id === item.clipId)?.cameraId || 'Local clip'}</span></td><td className="mono-data">{item.transactionTime}</td><td>{item.result?.candidateCount ?? '—'} candidate frames</td><td><StatusBadge status={item.status} /></td><td><ChevronRight size={15} /></td></tr>)}
          </tbody></table></div> : <EmptyLine icon={<History size={17} />} title="No investigation records yet" detail="Upload a clip and run the first transaction-time review." />}
        </section>

        <section className="panel activity-panel">
          <SectionTitle title="Local activity" detail="Recent system events" action={<span className="activity-clock"><Activity size={13} /> {events.length} EVENTS</span>} />
          {events.length ? <div className="activity-list">{events.slice(0, 5).map((event) => <div className="activity-item" key={event.id}><span className={`activity-pin ${event.severity === 'warning' ? 'pin-amber' : ''}`} /><div><strong>{event.message}</strong><time>{new Date(event.occurredAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</time></div></div>)}</div> : <EmptyLine icon={<Activity size={17} />} title="Activity will appear here" detail="Uploads, analyses and review decisions are recorded locally." />}
        </section>
      </div>
      <div className="engine-strip"><div className="engine-left"><span className={`engine-dot ${health ? 'engine-ready' : ''}`} /><strong>LOCAL ANALYSIS ENGINE</strong><span>•</span><span>{health?.models.person || 'Person detector'}</span><span>•</span><span>{health?.models.face || 'Face detector'}</span></div><button className="text-button" onClick={() => window.open('/api/docs', '_blank', 'noopener,noreferrer')}>API status <ArrowRight size={13} /></button></div>
    </>
  );
}

function CameraWall({ cameras, onUpload, compact = false }: { cameras: CameraSlot[]; onUpload: (cameraId: string) => void; compact?: boolean }) {
  const labels = [
    { id: 'ATM-01', label: 'Entry view', icon: <Eye size={15} /> },
    { id: 'ATM-02', label: 'Keypad view', icon: <Crosshair size={15} /> },
    { id: 'ATM-03', label: 'Cash slot', icon: <Database size={15} /> },
    { id: 'ATM-04', label: 'Exit view', icon: <ArrowDownRight size={15} /> },
  ];
  return <div className={`camera-grid ${compact ? 'camera-grid-compact' : ''}`}>
    {labels.map((item) => {
      const slot = cameras.find((camera) => camera.id === item.id);
      const clip = slot?.clips?.[0];
      return <article className={`camera-tile ${clip ? 'camera-has-clip' : ''}`} key={item.id}>
        <div className="camera-video-area">
          {clip ? clip.previewReady ? <video src={clip.videoUrl} poster={clip.posterUrl} muted controls playsInline preload="metadata" aria-label={`${item.id} ${item.label} local recording`} /> : <div className="camera-poster-preview"><img src={clip.posterUrl} alt={`${item.id} ${item.label} video poster`} /><span>Playback needs FFmpeg H.264 conversion</span></div> : <div className="camera-empty"><Camera size={19} /><span>No local clip assigned</span><button onClick={() => onUpload(item.id)}><Plus size={13} /> Add footage</button></div>}
          <span className={`camera-state ${clip ? 'camera-recorded' : ''}`}><i />{clip ? (clip.previewReady ? 'RECORDED' : 'POSTER ONLY') : 'EMPTY'}</span>
        </div>
        <div className="camera-meta"><div className="camera-label-icon">{item.icon}</div><div><strong>{item.id} <span>{item.label}</span></strong><small>{clip ? `${formatDuration(clip.duration)} · ${clip.width}×${clip.height} · ${clip.normalized ? 'H.264 review copy' : clip.codec}` : 'Waiting for sample footage'}</small></div><button className="icon-button camera-upload-mini" aria-label={`Upload clip to ${item.id}`} onClick={() => onUpload(item.id)}><Upload size={15} /></button></div>
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

function Library({ clips, cameras, onUpload, onDelete }: { clips: Clip[]; cameras: CameraSlot[]; onUpload: (id: string) => void; onDelete: (clip: Clip) => void }) {
  const [confirmDelete, setConfirmDelete] = useState('');
  const [integrity, setIntegrity] = useState<Record<string, { verified: boolean; checkedAt: string; notice: string }>>({});
  const [checking, setChecking] = useState('');
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
    <div className="library-callout"><div className="callout-mark"><ShieldCheck size={20} /></div><div><strong>Local vault with SHA-256 integrity checks</strong><span>Source and analyzed-file fingerprints are recorded at upload. Verify later to detect local byte changes; a matching hash does not prove who recorded the footage.</span></div><span className="callout-lock"><LockKeyhole size={15} /> LOCAL</span></div>
    <section className="panel library-panel"><SectionTitle title="ATM evidence channels" detail="Use separate local clips for each camera angle. These are recorded files, not live streams." action={<button className="button button-primary button-compact" onClick={() => onUpload('ATM-01')}><Upload size={15} /> Upload clip</button>} />
      <CameraWall cameras={cameras} onUpload={onUpload} />
    </section>
    <section className="panel library-files"><SectionTitle title="Uploaded footage" detail={`${clips.length} clip${clips.length === 1 ? '' : 's'} in this workspace`} />
      {clips.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>FILE</th><th>CAMERA</th><th>DURATION</th><th>RESOLUTION</th><th>SIZE</th><th>SHA-256 · SOURCE</th><th>INTEGRITY</th><th>UPLOADED</th><th /></tr></thead><tbody>{clips.map((clip) => <tr key={clip.id}><td><div className="file-cell"><FileVideo2 size={16} /><div><strong>{clip.filename}</strong><span>{clip.codec.toUpperCase()} · {clip.fps} FPS</span></div></div></td><td><span className="camera-id-pill">{clip.cameraId}</span></td><td className="mono-data">{formatDuration(clip.duration)}</td><td>{clip.width} × {clip.height}</td><td>{formatBytes(clip.sizeBytes)}</td><td><code className="hash-code" title={clip.sha256}>{clip.sha256.slice(0, 18)}…</code></td><td>{integrity[clip.id] ? <span className={`integrity-status ${integrity[clip.id].verified ? 'integrity-ok' : 'integrity-mismatch'}`} title={integrity[clip.id].notice}><i />{integrity[clip.id].verified ? 'Verified' : 'Mismatch'}</span> : <button className="verify-button" disabled={checking === clip.id} onClick={() => void verify(clip)}>{checking === clip.id ? <LoaderCircle size={12} className="spin" /> : <ShieldCheck size={12} />} Verify</button>}</td><td>{new Date(clip.uploadedAt).toLocaleDateString('en-IN')}</td><td className="delete-cell">{confirmDelete === clip.id ? <span className="confirm-delete"><button onClick={() => { onDelete(clip); setConfirmDelete(''); }}>Remove</button><button aria-label="Cancel remove" onClick={() => setConfirmDelete('')}><X size={14} /></button></span> : <button className="icon-button danger-hover" aria-label={`Remove ${clip.filename}`} onClick={() => setConfirmDelete(clip.id)}><Trash2 size={15} /></button>}</td></tr>)}</tbody></table></div> : <EmptyLine icon={<FolderOpen size={17} />} title="No video files uploaded" detail="Upload MP4, AVI, MOV, MKV, WMV, FLV or MPEG footage to start a review." />}
    </section>
  </>;
}

function Review({ analysisId, analysisSummary, onOpenSearch, onToast, onRefresh }: {
  analysisId: string; analysisSummary?: Analysis; onOpenSearch: (candidateId: string) => void; onToast: (toast: Toast) => void; onRefresh: () => void;
}) {
  const [record, setRecord] = useState<Analysis | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const load = useCallback(async () => {
    if (!analysisId) return;
    try { const result = await api.analysis(analysisId); setRecord(result); }
    catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not load analysis.' }); }
  }, [analysisId, onToast]);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 2500); return () => window.clearInterval(timer); }, [load]);

  const selected = record?.candidates.find((candidate) => candidate.id === selectedId) || record?.candidates[0];
  useEffect(() => { if (selected) setNote(selected.note || ''); }, [selected?.id]);

  const mark = async (status: Candidate['reviewStatus']) => {
    if (!selected) return;
    setBusy(true);
    try { await api.review(selected.id, status, note); await load(); onRefresh(); onToast({ kind: 'success', message: `Candidate marked ${status}. Review action recorded.` }); }
    catch (error) { onToast({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save review.' }); }
    finally { setBusy(false); }
  };

  const jumpToFrame = () => {
    if (!selected || !videoRef.current) return;
    videoRef.current.currentTime = selected.time;
    void videoRef.current.play();
  };

  if (!analysisId) return <section className="panel no-analysis"><ScanFace size={30} /><h2>Select an investigation</h2><p>Choose a completed investigation from Case desk to review the extracted candidates.</p></section>;
  const active = record || analysisSummary;
  return <>
    <div className="review-context-bar"><div className="context-icon"><FileVideo2 size={17} /></div><div><strong>{active?.clipName || 'Loading clip record…'}</strong><span>{active?.transactionRef || 'No transaction reference'} · {active?.timeMode === 'absolute' ? 'Bank timestamp' : 'Clip-relative time'} {active?.transactionTime}</span></div><div className="context-window"><Clock3 size={14} /> ±{active?.windowSeconds || 0}s search window</div><StatusBadge status={record?.status || active?.status || 'running'} />{record?.status === 'completed' && <a className="button button-outline button-compact evidence-download" href={`/api/evidence/${record.id}.pdf`} download><Download size={14} /> Evidence PDF</a>}</div>
    {record?.status === 'running' && <div className="processing-banner"><LoaderCircle size={17} className="spin" /><div><strong>Reviewing the transaction window locally</strong><span>Sampling video, detecting people and ranking face frame quality. You can leave this page open.</span></div><span className="process-time">ANALYSIS RUNNING</span></div>}
    {record?.status === 'failed' && <div className="error-banner"><AlertCircle size={18} /><div><strong>Analysis could not complete</strong><span>{record.error}</span></div></div>}
    <div className="review-grid">
      <section className="panel candidate-panel"><SectionTitle title="Face frame candidates" detail={record?.status === 'completed' ? `${record.candidates.length} frames · sorted by quality score` : 'Waiting for analysis results'} action={record?.status === 'completed' && record.candidates.length > 0 ? <span className="sorted-indicator"><SlidersHorizontal size={13} /> BEST FIRST</span> : undefined} />
        {record?.status === 'completed' && record.candidates.length ? <div className="candidate-grid">{record.candidates.map((candidate, index) => <button className={`candidate-card ${selected?.id === candidate.id ? 'candidate-selected' : ''}`} onClick={() => setSelectedId(candidate.id)} key={candidate.id}>
          <div className="candidate-image-wrap"><img src={candidate.imageUrl} alt={`Face candidate at ${candidate.timeLabel}`} /><span className="candidate-rank">{String(index + 1).padStart(2, '0')}</span><span className={`quality-badge ${candidate.score >= 75 ? 'quality-high' : candidate.score >= 50 ? 'quality-mid' : 'quality-low'}`}>{Math.round(candidate.score)}<small> / 100</small></span></div>
          <div className="candidate-card-meta"><strong>{candidate.timeLabel}</strong><span>TRACK {String(candidate.trackId).padStart(2, '0')}</span></div>
          <div className="candidate-mini-metrics"><i style={{ width: `${candidate.score}%` }} /></div>
          {candidate.flags.length > 0 && <div className="candidate-flags">{candidate.flags.slice(0, 2).map((flag) => <span key={flag}>{flag}</span>)}</div>}
        </button>)}</div> : record?.status === 'completed' ? <div className="no-candidates"><div className="no-candidate-icon"><ScanFace size={23} /></div><h3>No face candidates found</h3><p>Try a wider time window or a clearer clip export. Low resolution, occlusion and camera angle can affect detection.</p><div className="no-candidate-meta"><span>{record.result.sampledFrames || 0} frames sampled</span><span>{record.result.peopleSeen || 0} person tracks</span></div></div> : <div className="candidate-loading"><LoaderCircle size={20} className="spin" /><span>Candidate frames appear here when analysis finishes.</span></div>}
      </section>

      <aside className="review-side-stack">
        <section className="panel selected-panel"><SectionTitle title="Selected frame" detail={selected ? `Track ${String(selected.trackId).padStart(2, '0')} · ${selected.timeLabel}` : 'Choose a candidate'} />
          {selected ? <>
            <div className="selected-image"><img src={selected.imageUrl} alt="Selected candidate face crop" /><span className="selected-score">{Math.round(selected.score)}<small> QUALITY</small></span></div>
            <button className="text-button frame-link" onClick={jumpToFrame}><Play size={13} /> Find this time in clip <span>{selected.timeLabel}</span></button>
            <QualityBars metrics={selected.metrics} />
            <div className="review-flags"><strong>Reliability flags</strong>{selected.flags.length ? selected.flags.map((flag) => <span className="flag-chip" key={flag}><AlertCircle size={12} />{flag}</span>) : <span className="clear-flag"><Check size={12} /> No quality flags</span>}</div>
            <label className="review-note"><span>Investigator note</span><textarea value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Add an observation or comparison note…" /></label>
            <div className="review-actions"><button className={`button button-outline ${selected.reviewStatus === 'rejected' ? 'button-rejected' : ''}`} disabled={busy} onClick={() => void mark('rejected')}><X size={14} /> Exclude</button><button className="button button-primary" disabled={busy} onClick={() => void mark('selected')}><UserRoundCheck size={15} /> Mark for review</button></div>
            <button className="button button-search" onClick={() => onOpenSearch(selected.id)}><Search size={15} /> Search other clips <ArrowRight size={15} /></button>
          </> : <div className="selected-empty"><ScanFace size={22} /><p>Candidate details and review actions appear here.</p></div>}
        </section>
        <section className="panel clip-player-panel"><SectionTitle title="Source footage" detail="Stored locally · use controls to inspect context" />{record ? <video ref={videoRef} src={`/api/clips/${record.clipId}/video`} controls muted playsInline preload="metadata" /> : <div className="video-skeleton"><LoaderCircle size={18} className="spin" /></div>}<div className="source-meta"><span><LockKeyhole size={12} /> LOCAL FILE</span><span>{record?.result?.windowStart !== undefined ? `${formatDuration(record.result.windowStart)}–${formatDuration(record.result.windowEnd || 0)}` : 'Transaction window'}</span></div></section>
      </aside>
    </div>
    {record?.status === 'completed' && <section className="panel timeline-panel"><SectionTitle title="Transaction timeline" detail="Candidate frames within the selected time window" />
      <div className="timeline-track"><div className="timeline-range"><span>{formatDuration(record.result.windowStart || 0)}</span><div className="timeline-line"><i /><i /><i /></div><span>{formatDuration(record.result.windowEnd || 0)}</span></div><div className="transaction-marker" style={{ left: `${Math.min(92, Math.max(8, ((record.result.windowStart || 0) / Math.max(record.result.windowEnd || 1, 1)) * 100))}%` }}><span>{record.transactionTime}</span><i /></div>{record.candidates.map((candidate, index) => <button key={candidate.id} className="timeline-candidate" style={{ left: `${Math.min(96, Math.max(2, ((candidate.time - (record.result.windowStart || 0)) / Math.max((record.result.windowEnd || 1) - (record.result.windowStart || 0), 1)) * 100))}%` }} title={`${candidate.timeLabel} · score ${Math.round(candidate.score)}`} onClick={() => setSelectedId(candidate.id)}><i style={{ height: `${22 + candidate.score * 0.55}px` }} /><span>{index === 0 ? candidate.timeLabel : ''}</span></button>)}</div>
      <div className="timeline-legend"><span><i className="legend-transaction" />Transaction time</span><span><i className="legend-candidate" />Detected face frame</span><span>{record.result.sampledFrames || 0} frames sampled</span></div>
    </section>}
    <div className="review-disclaimer"><Shield size={14} /><span>Human verification required. Visual similarity and quality scores are aids for authorised review, not identity verification or guilt findings.</span></div>
  </>;
}

function QualityBars({ metrics }: { metrics: Candidate['metrics'] }) {
  const rows = [['Sharpness', metrics.sharpness], ['Illumination', metrics.illumination], ['Pose', metrics.pose], ['Face size', metrics.faceSize]] as [string, number][];
  return <div className="quality-breakdown"><div className="quality-heading"><strong>Frame quality signals</strong><span>0–100</span></div>{rows.map(([label, value]) => <div className="quality-row" key={label}><span>{label}</span><div><i style={{ width: `${value}%` }} /></div><strong>{value}</strong></div>)}</div>;
}

function SearchWorkspace({ analyses, candidateId, onCandidateChange, onReview }: {
  analyses: Analysis[]; candidateId: string; onCandidateChange: (id: string) => void; onReview: (id: string) => void;
}) {
  const [matches, setMatches] = useState<(Candidate & { similarity: number; filename: string })[]>([]);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const candidates = useMemo(() => analyses.flatMap((analysis) => analysis.candidates.map((candidate) => ({ ...candidate, clipName: analysis.clipName }))), [analyses]);
  const selected = candidates.find((candidate) => candidate.id === candidateId);

  useEffect(() => { setMatches([]); setNotice(''); }, [candidateId]);

  const search = async () => {
    if (!candidateId) return;
    setBusy(true);
    try { const result = await api.search(candidateId); setMatches(result.matches); setNotice(result.notice); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Search failed.'); }
    finally { setBusy(false); }
  };

  return <div className="search-layout">
    <section className="panel search-source-panel"><SectionTitle title="Choose a face frame" detail="Select a reviewed candidate as the search reference." />
      <label className="field-label" htmlFor="candidate-source">Reference candidate</label>
      <div className="select-wrap"><ScanFace size={16} /><select id="candidate-source" value={candidateId} onChange={(event) => onCandidateChange(event.target.value)}><option value="">Select candidate…</option>{candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.clipName} · {candidate.timeLabel} · score {Math.round(candidate.score)}</option>)}</select><ChevronDown size={15} /></div>
      {selected && <div className="search-reference"><img src={selected.imageUrl} alt="Search reference candidate" /><div><strong>{selected.clipName}</strong><span>{selected.timeLabel} · Track {selected.trackId}</span><b>Frame quality {Math.round(selected.score)}/100</b></div></div>}
      <div className="search-method"><Fingerprint size={17} /><div><strong>Local appearance comparison</strong><span>Compares visual descriptors from this workspace only. No names, watchlists or external databases.</span></div></div>
      <button className="button button-primary search-submit" disabled={!candidateId || busy} onClick={() => void search}>{busy ? <LoaderCircle size={16} className="spin" /> : <Search size={16} />}{busy ? 'Comparing local clips…' : 'Search other clips'}<ArrowRight size={16} /></button>
    </section>

    <section className="panel search-results-panel"><SectionTitle title="Similar candidates" detail={matches.length ? `${matches.length} results from other clips` : 'Search results appear here'} action={matches.length > 0 ? <span className="sorted-indicator">BEST MATCH FIRST</span> : undefined} />
      {notice && <div className="search-notice"><AlertCircle size={14} />{notice}</div>}
      {matches.length ? <div className="match-list">{matches.map((match) => <article className="match-row" key={match.id}><img src={match.imageUrl} alt="Similar candidate frame" /><div className="match-main"><strong>{match.filename}</strong><span>{match.timeLabel} · Track {match.trackId} · Frame quality {Math.round(match.score)}</span><div className="match-flags">{match.flags.map((flag) => <small key={flag}>{flag}</small>)}</div></div><div className="similarity-score"><strong>{Math.round(match.similarity)}%</strong><span>visual similarity</span></div><button className="button button-outline button-compact" onClick={() => onReview(match.analysisId)}>Review clip <ChevronRight size={14} /></button></article>)}</div> : <div className="search-empty"><div className="search-empty-icon"><Search size={24} /></div><h3>{busy ? 'Searching local clips' : candidateId ? 'No matches found' : 'Choose a reference candidate'}</h3><p>{busy ? 'Only other clips in this local workspace are being compared.' : candidateId ? 'No candidate crossed the baseline similarity threshold. A no-match result is not proof of absence.' : 'Run an analysis and choose a candidate frame to compare it with other uploaded clips.'}</p></div>}
    </section>
  </div>;
}

function Reports({ data, analyses, events }: { data: Awaited<ReturnType<typeof api.reports>> | null; analyses: Analysis[]; events: EventItem[] }) {
  const completed = data?.analyses.completed || 0;
  const failed = data?.analyses.failed || 0;
  const reviewed = data?.reviews.selected || 0;
  const rejected = data?.reviews.rejected || 0;
  const weeks = analyses.slice(0, 6).reverse();
  return <>
    <div className="report-summary"><Stat label="Analyses completed" value={completed} detail="Local processing jobs" icon={<BadgeCheck size={18} />} tone="teal" /><Stat label="Candidates marked" value={reviewed} detail="For further human review" icon={<UserRoundCheck size={18} />} tone="amber" /><Stat label="Average frame score" value={`${data?.quality.average ?? 0}`} detail="Across extracted candidates" icon={<Gauge size={18} />} /><Stat label="Processing issues" value={failed} detail="Jobs needing attention" icon={<AlertCircle size={18} />} tone={failed ? 'red' : 'navy'} /></div>
    <div className="reports-grid">
      <section className="panel report-panel"><SectionTitle title="Review outcomes" detail="Candidate status distribution" />
        {[['Marked for review', reviewed, 'bar-teal'], ['Excluded by reviewer', rejected, 'bar-red'], ['Not yet reviewed', data?.reviews.unreviewed || 0, 'bar-amber']].map(([label, value, color]) => <div className="report-bar-row" key={String(label)}><div><span>{label}</span><strong>{value}</strong></div><div className="report-bar-track"><i className={String(color)} style={{ width: `${Math.max(value ? 4 : 0, (Number(value) / Math.max(reviewed + rejected + (data?.reviews.unreviewed || 0), 1)) * 100)}%` }} /></div></div>)}
        <div className="report-footnote"><ShieldCheck size={14} /> Review labels are operator decisions, not automated verdicts.</div>
      </section>
      <section className="panel report-panel"><SectionTitle title="Recent analysis windows" detail="Transaction-linked review activity" />
        {weeks.length ? <div className="mini-timeline">{weeks.map((item) => <div className="mini-time-item" key={item.id}><div className="mini-time-bar"><i style={{ height: `${Math.max(10, (item.result?.candidateCount || 1) * 18)}px` }} className={item.status === 'failed' ? 'bar-fill-red' : 'bar-fill-navy'} /></div><span>{new Date(item.createdAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span><small>{item.result?.candidateCount ?? '—'} frames</small></div>)}</div> : <EmptyLine icon={<BarChart3 size={17} />} title="No analysis history" detail="Reports build from completed local investigations." />}
        <div className="chart-axis"><span>Older</span><span>Each bar = one investigation</span><span>Recent</span></div>
      </section>
    </div>
    <section className="panel report-events"><SectionTitle title="Event register" detail="Processing events with timestamps" />{events.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>EVENT</th><th>DETAIL</th><th>SEVERITY</th><th>TIME</th></tr></thead><tbody>{events.slice(0, 20).map((event) => <tr key={event.id}><td><strong>{event.kind}</strong></td><td>{event.message}</td><td><span className={`severity severity-${event.severity}`}>{event.severity}</span></td><td>{new Date(event.occurredAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</td></tr>)}</tbody></table></div> : <EmptyLine icon={<Activity size={17} />} title="No system events yet" detail="Processing events are recorded here once a clip is analysed." />}</section>
  </>;
}

function Audit({ items, events, integrity }: { items: AuditItem[]; events: EventItem[]; integrity: AuditIntegrity | null }) {
  const [filter, setFilter] = useState('all');
  const combined = useMemo(() => [
    ...items.map((item) => ({ id: item.id, kind: item.action, message: item.note, time: item.occurredAt, source: 'Operator action', severity: 'info' })),
    ...events.map((item) => ({ id: item.id, kind: item.kind, message: item.message, time: item.occurredAt, source: 'System event', severity: item.severity })),
  ].sort((a, b) => b.time.localeCompare(a.time)), [items, events]);
  const visible = filter === 'all' ? combined : combined.filter((item) => item.source === filter);
  return <section className="panel audit-panel"><SectionTitle title="Audit log" detail="Local record of file handling, analysis and candidate review actions" action={<div className="audit-filters"><button className={filter === 'all' ? 'filter-active' : ''} onClick={() => setFilter('all')}>All</button><button className={filter === 'Operator action' ? 'filter-active' : ''} onClick={() => setFilter('Operator action')}>Operator</button><button className={filter === 'System event' ? 'filter-active' : ''} onClick={() => setFilter('System event')}>System</button></div>} />
    <div className={`audit-chain ${integrity?.verified ? 'audit-chain-ok' : integrity ? 'audit-chain-failed' : ''}`} role="status">
      {integrity?.verified ? <BadgeCheck size={16} /> : <ShieldCheck size={16} />}
      <strong>{integrity ? (integrity.verified ? 'AUDIT CHAIN VERIFIED' : 'AUDIT CHAIN CHECK FAILED') : 'CHECKING AUDIT CHAIN'}</strong>
      {integrity && <span>{integrity.entriesChecked} entries checked</span>}
      {!integrity?.verified && integrity?.reason && <span>{integrity.reason}</span>}
    </div>
    {visible.length ? <div className="table-scroll"><table className="data-table audit-table"><thead><tr><th>TIME</th><th>ACTION</th><th>DETAIL</th><th>TYPE</th><th>SEVERITY</th></tr></thead><tbody>{visible.map((item) => <tr key={item.id}><td className="mono-data">{new Date(item.time).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' })}</td><td><strong>{item.kind}</strong></td><td>{item.message}</td><td><span className="source-label">{item.source}</span></td><td><span className={`severity severity-${item.severity}`}>{item.severity}</span></td></tr>)}</tbody></table></div> : <EmptyLine icon={<FileClock size={17} />} title="No audit entries" detail="Upload, analysis and review actions appear here." />}
    <div className="audit-footnote"><LockKeyhole size={14} /> Hash-linked audit records reveal accidental or partial changes; privileged database rewrites require external signed checkpoints to detect.</div>
  </section>;
}

export default App;
