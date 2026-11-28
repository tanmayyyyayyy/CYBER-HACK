import { useEffect, useRef, useState } from 'react';
import LoginHeadline from './LoginHeadline';
import { api, MAX_CLIP_BYTES, type Analysis, type AuthUser, type Candidate, type Clip, type FaceEnhancement, formatDuration, formatBytes } from './api';
import FrameInspector from './FrameInspector';
import CrossCameraFaceReview, { TrackFacePicture } from './FaceEnhancement';
import '@fontsource/noto-sans/400.css';
import '@fontsource/noto-sans/700.css';
import '@fontsource/noto-sans-devanagari/400.css';
import '@fontsource/noto-sans-devanagari/700.css';
import './guided.css';

const steps = ['Login', 'Naya case', 'Video upload', 'File check', 'Transaction', 'Scan', 'Person chunein', 'Best frames', 'Dusri clips', 'Evidence sheet'];
type Draft = { step: number; caseNumber: string; atmId: string; clipId: string; analysisId: string; selectedId: string; uncertain: boolean; reviewed: boolean; timeMode: 'clip' | 'absolute'; transactionTime: string; clipStart: string; windowSeconds: number; quickScan: boolean; note: string; extraClipId?: string; extraAnalysisId?: string };
const fresh: Draft = { step: 1, caseNumber: '', atmId: '', clipId: '', analysisId: '', selectedId: '', uncertain: false, reviewed: false, timeMode: 'clip', transactionTime: '', clipStart: '', windowSeconds: 30, quickScan: true, note: '' };
function savedDraft(): Draft { try { return { ...fresh, ...JSON.parse(localStorage.getItem('drishti-tool-draft') || '{}') }; } catch { return fresh; } }
function message(error: unknown) { return error instanceof Error && error.name === 'AbortError' ? 'Upload ka wait roka gaya. Server par file check kuch der chal sakta hai.' : error instanceof Error ? error.message : 'Kuch galat hua. Dobara koshish karein.'; }

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [setup, setSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<Draft>(savedDraft);
  const [clips, setClips] = useState<Clip[]>([]);
  const [extraAnalysis, setExtraAnalysis] = useState<Analysis | null>(null);
  const [extraTime, setExtraTime] = useState('');
  const [extraCamera, setExtraCamera] = useState('ATM-02');
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [reviewPicture, setReviewPicture] = useState<{ analysisId: string; trackId: number; result: FaceEnhancement } | null>(null);
  const [matches, setMatches] = useState<(Candidate & { similarity: number; filename: string })[]>([]);
  const [inspectedCandidate, setInspectedCandidate] = useState<Candidate | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [uploadSeconds, setUploadSeconds] = useState(0);
  const uploadController = useRef<AbortController | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [pending, setPending] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const update = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }));
  const go = (step: number) => { setError(''); update({ step: Math.max(1, Math.min(9, step)) }); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const clip = clips.find((item) => item.id === draft.clipId);
  const candidates = analysis?.candidates || [];
  const selected = candidates.find((item) => item.id === draft.selectedId);
  const trackFrames = selected && selected.trackId > 0 ? candidates.filter(
    (item) => item.trackId === selected.trackId && item.reviewStatus !== 'rejected',
  ) : [];

  useEffect(() => { localStorage.setItem('drishti-tool-draft', JSON.stringify(draft)); }, [draft]);
  useEffect(() => {
    if (!uploading) return;
    const started = Date.now();
    const timer = window.setInterval(() => setUploadSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [uploading]);
  useEffect(() => {
    let alive = true;
    api.authBootstrap().then(async (result) => { if (!alive) return; setSetup(result.needsAdministrator); if (result.needsAdministrator) setAuthMode('signup'); if (result.authenticated) { const session = await api.authMe(); if (alive) setUser(session.user); } }).catch(() => { if (alive) setError('Local server se connection nahi bana. Backend start karein.'); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  useEffect(() => { if (user) api.clips().then(setClips).catch((err) => setError(message(err))); }, [user]);
  useEffect(() => {
    if (!user || !draft.analysisId) return;
    const id = draft.analysisId;
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const result = await api.analysis(id);
        if (!active) return;
        setAnalysis(result);
        if (result.status === 'queued' || result.status === 'running') {
          timer = window.setTimeout(() => void poll(), 1500);
        }
      } catch (err) {
        if (active) {
          setError(message(err));
          timer = window.setTimeout(() => void poll(), 3000);
        }
      }
    };
    void poll();
    return () => { active = false; window.clearTimeout(timer); };
  }, [user, draft.analysisId]);

  useEffect(() => {
    if (!user || draft.step !== 8 || !draft.extraAnalysisId) return;
    const id = draft.extraAnalysisId;
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const result = await api.analysis(id);
        if (!active) return;
        setExtraAnalysis(result);
        if (result.status === 'queued' || result.status === 'running') {
          timer = window.setTimeout(() => void poll(), 1500);
        }
      } catch (err) {
        if (active) {
          setError(message(err));
          setDraft((current) => current.extraAnalysisId === id ? { ...current, extraAnalysisId: '' } : current);
        }
      }
    };
    void poll();
    return () => { active = false; window.clearTimeout(timer); };
  }, [user, draft.step, draft.extraAnalysisId]);

  const run = async (work: () => Promise<void>) => { setBusy(true); setError(''); try { await work(); } catch (err) { setError(message(err)); } finally { setBusy(false); } };
  const submitAuth = (event: React.FormEvent) => { event.preventDefault(); void run(async () => {
    if (authMode === 'login') { const result = await api.authLogin(email, password); setUser(result.user); }
    else { const result = await api.authSignup(displayName, email, password); if (result.approvalRequired) { setPending(true); setAuthMode('login'); } else setUser(result.user); }
    setShowPassword(false);
  }); };
  const upload = (file: File | undefined, additional = false) => {
    if (!file) return;
    if (file.size > MAX_CLIP_BYTES) { setError('Video 20 GB se bada hai. Chhota clip upload karein.'); return; }
    const controller = new AbortController();
    uploadController.current = controller;
    setUploading(true);
    setUploadPercent(0);
    setUploadSeconds(0);
    void run(async () => {
      const result = await api.upload(file, additional ? extraCamera : 'ATM-01', '', setUploadPercent, controller.signal);
      setClips((items) => [result, ...items]);
      if (additional) {
        setExtraTime('');
        setExtraAnalysis(null);
        update({ extraClipId: result.id, extraAnalysisId: '' });
      } else {
        update({ clipId: result.id, analysisId: '', selectedId: '', reviewed: false, uncertain: false, extraClipId: '', extraAnalysisId: '' });
        go(3);
      }
    }).finally(() => { setUploading(false); uploadController.current = null; });
  };
  const scan = () => void run(async () => {
    if (!clip) throw new Error('Pehle video chunein.');
    if (!draft.transactionTime) throw new Error('Transaction ka time batayein.');
    if (draft.timeMode === 'absolute' && !draft.clipStart) throw new Error('CCTV video ka shuru hone wala time batayein.');
    const result = await api.analyze({ clip_id: clip.id, transaction_time: draft.transactionTime, time_mode: draft.timeMode, clip_start_time: draft.clipStart, transaction_ref: '', case_ref: draft.caseNumber, window_seconds: draft.windowSeconds, quick_scan: draft.quickScan });
    update({ analysisId: result.id, selectedId: '', uncertain: false, reviewed: false, step: 5 }); setAnalysis(null);
  });
  const extraClip = clips.find((item) => item.id === draft.extraClipId && item.id !== draft.clipId);
  const activeExtraAnalysis = extraAnalysis?.id === draft.extraAnalysisId ? extraAnalysis : null;
  const scanningExtra = Boolean(draft.extraAnalysisId && (!activeExtraAnalysis || activeExtraAnalysis.status === 'queued' || activeExtraAnalysis.status === 'running'));
  const scanExtra = (event: React.FormEvent) => {
    event.preventDefault();
    if (!extraClip || busy || scanningExtra) return;
    void run(async () => {
      const result = await api.analyze({
        clip_id: extraClip.id, transaction_time: extraTime, time_mode: 'clip',
        clip_start_time: '', transaction_ref: '', case_ref: draft.caseNumber, window_seconds: draft.windowSeconds, quick_scan: draft.quickScan,
      });
      update({ extraAnalysisId: result.id });
      setExtraAnalysis(null);
    });
  };

  const confirm = (candidate?: Candidate) => void run(async () => {
    if (candidate) { await api.review(candidate.id, 'selected', draft.note); update({ selectedId: candidate.id, uncertain: false, reviewed: true }); }
    else { if (analysis) await api.recordFootageObservation(analysis.id, { time: analysis.transactionOffsetSeconds || 0, visibility: 'unavailable', note: draft.note || 'Officer could not confirm a transaction person.', incidentId: '' }); update({ selectedId: '', uncertain: true, reviewed: true }); }
    go(7);
  });
  const search = () => void run(async () => { if (draft.selectedId) { const result = await api.search(draft.selectedId); setMatches(result.matches); } go(8); });

  if (loading) return <main className="center"><p>Drishti khul raha hai…</p></main>;
  if (!user) return <main className="auth-layout">
    <div className="auth-brand">
      <img src="/assets/drishti-logo-original.png" alt="Drishti Digital Forensics" />
      <LoginHeadline />
      <p>ATM video ko step by step dekhein aur apni jaanch record karein.</p>
    </div>
    <div className="auth-box">
      <span className="overline">Local access</span>
      <h2>{authMode === 'login' ? 'Login karein' : setup ? 'Admin account banayein' : 'Account banayein'}</h2>
      <p>Sirf authorised investigator ya admin ke liye.</p>
      <form onSubmit={submitAuth}>
        {authMode === 'signup' && <label>Aapka naam<input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="name" /></label>}
        <label>Email<input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
        <div className="password-field">
          <label htmlFor="auth-password">Password</label>
          <div className="password-input">
            <input id="auth-password" required type={showPassword ? 'text' : 'password'} minLength={authMode === 'signup' ? 12 : 1} maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={authMode === 'login' ? 'current-password' : 'new-password'} />
            <button type="button" className="password-toggle" aria-label={showPassword ? 'Password chhupayein' : 'Password dikhayein'} aria-pressed={showPassword} onClick={() => setShowPassword((shown) => !shown)}>{showPassword ? 'Chhupayein' : 'Dikhayein'}</button>
          </div>
          {authMode === 'signup' && <small>Kam se kam 12 characters likhein.</small>}
        </div>
        <button className="primary" disabled={busy}>{busy ? 'Rukiye…' : authMode === 'login' ? 'Login' : 'Account banayein'}</button>
      </form>
      {pending && <p className="notice">Account bana hai. Admin approval ke baad login karein.</p>}
      {error && <p role="alert" className="error">{error}</p>}
      <button className="link-button" onClick={() => { setAuthMode(authMode === 'login' ? 'signup' : 'login'); setShowPassword(false); setError(''); setPending(false); }}>{authMode === 'login' ? 'Naya account banayein' : 'Login par wapas'}</button>
    </div>
  </main>;

  return <div className="shell"><header className="app-header"><div className="brand"><img src="/assets/drishti-logo-original.png" alt="Drishti Digital Forensics" /><span>Drishti</span></div><span className="header-case">{draft.caseNumber || 'Naya case'}</span><div className="header-right"><button onClick={() => setHelpOpen(true)}>Help / FAQ</button><a href="/legacy?tab=desk">Advanced tools</a><span>{user.displayName}</span><button onClick={() => void run(async () => { await api.authLogout(); setUser(null); })}>Log out</button></div></header><div className="app-body"><nav className="step-nav" aria-label="Case steps"><p>Jaanch ka raasta</p>{steps.slice(1).map((name, index) => <button key={name} disabled={index + 1 > draft.step || index + 1 === 5 && !draft.analysisId} className={draft.step === index + 1 ? 'active' : ''} onClick={() => go(index + 1)}><span>{index + 1}</span>{name}</button>)}</nav><main className="work"><div className="work-top"><span>STEP {draft.step} / 9</span><button onClick={() => { if (window.confirm('Naya case shuru karein? Is screen ka saved progress hat jayega.')) { setDraft(fresh); setAnalysis(null); setMatches([]); } }}>Naya case</button></div>{error && <div role="alert" className="error">{error}</div>}
    {draft.step === 1 && <section className="task"><h1>Naya case shuru karein</h1><p>Case number aur ATM ID likhein. Baaki cheezein agle screens par aayengi.</p><div className="fields"><label>Case number<input value={draft.caseNumber} onChange={(e) => update({ caseNumber: e.target.value })} placeholder="Jaise FIR-2026-014" maxLength={40} /></label><label>ATM ID<input value={draft.atmId} onChange={(e) => update({ atmId: e.target.value })} placeholder="Jaise ATM-014" maxLength={40} /></label></div><button className="primary" disabled={!draft.caseNumber.trim() || !draft.atmId.trim()} onClick={() => go(2)}>Aage badhein <span>→</span></button></section>}
    {draft.step === 2 && <section className="task">
      <h1>Video chunein</h1>
      <p>ATM ka video ya DVR export upload karein. Original file local machine par rakhi jayegi.</p>
      <label className="upload-zone">
        <span className="upload-symbol">↑</span>
        <strong>{uploading ? uploadPercent < 100 ? `Video upload ho raha hai: ${uploadPercent}%` : 'Video check ho raha hai…' : 'Video file yahan chunein'}</strong>
        <small>MP4, AVI, MOV, MKV ya DVR export. Max 20 GB.</small>
        <input type="file" accept="video/*,.dav,.h264,.264,.asf,.ts,.m4v,.vob" disabled={busy} onChange={(e) => { upload(e.target.files?.[0]); e.currentTarget.value = ''; }} />
      </label>
      {uploading && <div className="upload-progress" role="status">
        <progress max={100} value={uploadPercent} aria-label="Video upload progress" />
        <p>{uploadPercent < 100 ? 'File bheji ja rahi hai.' : 'File pahunch gayi. Video ka format aur quality check ho rahe hain. Badi recording mein kuch minute lag sakte hain.'}</p>
        <small>{Math.floor(uploadSeconds / 60)} min {uploadSeconds % 60} sec hue</small>
        <button type="button" className="secondary" onClick={() => uploadController.current?.abort()}>Wait rok dein</button>
      </div>}
      {clips.length > 0 && <div className="compact-list"><h2>Pehle se available</h2>{clips.slice(0, 5).map((item) => <button key={item.id} onClick={() => { update({ clipId: item.id }); go(3); }}>{item.filename}<span>Chunein →</span></button>)}</div>}
      <Back onClick={() => go(1)} />
    </section>}
    {draft.step === 3 && <section className="task"><h1>File theek hai?</h1><p>Video ki jankari check karein. Original file ka record safe rehta hai.</p>{clip ? <><div className="file-preview"><video src={clip.videoUrl} poster={clip.posterUrl} controls preload="metadata" /><div><strong>{clip.filename}</strong><dl><dt>Video format</dt><dd>{clip.codec || 'Unknown'}</dd><dt>Size</dt><dd>{clip.width} × {clip.height}</dd><dt>Duration</dt><dd>{formatDuration(clip.duration)}</dd><dt>File size</dt><dd>{formatBytes(clip.sizeBytes)}</dd></dl></div></div><div className="notice">{clip.normalized ? 'Video ko chalne layak format mein badla gaya hai. Original safe hai.' : clip.previewReady ? 'Video chalne ke liye ready hai.' : 'Preview nahi chal raha. DVR software se MP4 (H.264) export karein, phir dobara upload karein.'}</div><button className="primary" disabled={!clip.previewReady} onClick={() => go(4)}>File sahi hai, aage badhein →</button></> : <p>Video nahi mila. Pichhle step par upload karein.</p>}<Back onClick={() => go(2)} /></section>}
    {draft.step === 4 && <section className="task"><h1>Transaction ka time batayein</h1><p>Isi time ke aas paas ka video scan hoga.</p><div className="choice-row"><button className={draft.timeMode === 'clip' ? 'chosen' : ''} onClick={() => update({ timeMode: 'clip', transactionTime: '' })}>Video ka time</button><button className={draft.timeMode === 'absolute' ? 'chosen' : ''} onClick={() => update({ timeMode: 'absolute', transactionTime: '' })}>Bank ka time</button></div><div className="fields"><label>{draft.timeMode === 'clip' ? 'Video mein time (HH:MM:SS)' : 'Bank transaction ka time'}<input required type={draft.timeMode === 'clip' ? 'text' : 'datetime-local'} placeholder={draft.timeMode === 'clip' ? '00:02:30' : undefined} pattern={draft.timeMode === 'clip' ? '\\d{2,3}:\\d{2}:\\d{2}' : undefined} value={draft.transactionTime} onChange={(e) => update({ transactionTime: e.target.value })} /></label>{draft.timeMode === 'absolute' && <label>CCTV video kab shuru hua?<input type="datetime-local" value={draft.clipStart} onChange={(e) => update({ clipStart: e.target.value })} /><small>Bank aur CCTV ki ghadi alag ho sakti hai. Dono time dekar sahi jagah dhoondhein.</small></label>}<label>Kitne time tak dekhein?<select value={draft.windowSeconds} onChange={(e) => update({ windowSeconds: Number(e.target.value) })}><option value={15}>15 second dono taraf</option><option value={30}>30 second dono taraf</option><option value={60}>1 minute dono taraf</option><option value={120}>2 minute dono taraf</option><option value={300}>5 minute dono taraf</option></select></label>
      <label>Scan mode<select value={draft.quickScan ? 'quick' : 'detailed'} onChange={(event) => update({ quickScan: event.target.value === 'quick' })}>
        <option value="quick">Quick scan</option><option value="detailed">Detailed scan</option>
      </select><small>Quick scan kam frames check karta hai. Chehra kuch pal ke liye dikhe toh Detailed scan chunein.</small></label>
    </div><button className="primary" disabled={busy || !draft.transactionTime || draft.timeMode === 'absolute' && !draft.clipStart} onClick={scan}>{busy ? 'Scan shuru ho raha hai…' : 'Video scan karein →'}</button><Back onClick={() => go(3)} /></section>}
    {draft.step === 5 && <section className="task">
      <h1>{analysis?.status === 'completed' ? 'Video scan poora hua' : analysis?.status === 'failed' ? 'Video scan poora nahi hua' : 'Video scan ho raha hai'}</h1>
      <p>{draft.quickScan ? 'Quick scan' : 'Detailed scan'} · {draft.transactionTime} ke aas paas ±{draft.windowSeconds} sec.</p>
      <div className="scan-box" role="status">
        {analysis?.status === 'completed' ? <strong>{analysis.result.peopleSeen || 0} person tracks · {analysis.candidates.length} face frames</strong>
          : analysis?.status === 'failed' ? <strong>{analysis.error}</strong>
          : <>
            <strong>{analysis?.status === 'queued' ? 'Scan queue mein hai' : 'Frames check ho rahe hain'}</strong>
            {analysis?.status === 'running' && <><progress aria-label="Scan progress" max={100} value={analysis.result.progressPercent ?? 0} />
              <span>{analysis.result.progressPercent ?? 0}% · {analysis.result.sampledFrames ?? 0} frames checked</span></>}
            {analysis?.status === 'queued' && <span>Pichhla scan khatam hote hi yeh scan shuru hoga.</span>}
          </>}
      </div>
      {analysis?.status === 'completed' && <button className="primary" onClick={() => go(6)}>Person dekhein →</button>}
      {analysis?.status === 'failed' && <button className="secondary" onClick={() => go(4)}>Time badal kar dobara karein</button>}
      {analysis?.status === 'completed' && analysis.result.scanMode === 'quick' &&
        <button className="back" onClick={() => { update({ quickScan: false }); go(4); }}>Detailed scan karein</button>}
      <Back onClick={() => go(4)} />
    </section>}
    {draft.step === 6 && <section className="task">
      <h1>Transaction wala person kaun ho sakta hai?</h1>
      <p>Face aur poora scene dekhkar khud faisla karein. Sirf photo se identity confirm nahi hoti.</p>
      {analysis?.result.primaryTerminalTrack != null && <div className="notice">System ko ATM ke paas Person {analysis.result.primaryTerminalTrack} relevant laga. Yeh sirf suggestion hai.</div>}
      {candidates.length ? <div className="person-review-list">{candidates.slice(0, 6).map((item) => <article className={draft.selectedId === item.id ? 'person-review-row chosen' : 'person-review-row'} key={item.id}>
        <button type="button" className="person-review-choice" aria-pressed={draft.selectedId === item.id} onClick={() => update({ selectedId: item.id, uncertain: false })}>
          <img src={item.imageUrl} alt={`Person ${item.trackId} ka face crop`} />
          <span className="person-review-copy"><strong>Person {item.trackId}</strong><small>Video time {item.timeLabel}</small><small>Frame quality {Math.round(item.score)}/100</small><em>{draft.selectedId === item.id ? 'Aapne chuna hai' : 'Chunne ke liye dabayein'}</em></span>
        </button>
        <button type="button" className="person-review-open" onClick={() => setInspectedCandidate(item)}>Poora scene dekhein ↗</button>
      </article>)}</div> : <div className="notice">Saaf chehra nahi mila. “Pakka nahi” chun sakte hain.</div>}
      <label className="person-review-note">Officer ka note (optional)<textarea value={draft.note} onChange={(e) => update({ note: e.target.value })} placeholder="Aapne kya dekha?" maxLength={500} /></label>
      <div className="actions person-review-actions"><button className="secondary" disabled={busy} onClick={() => confirm()}>Pakka nahi</button><button className="primary" disabled={busy || !selected} onClick={() => confirm(selected)}>Is person ko chunein →</button></div>
      <Back onClick={() => go(5)} />
    </section>}
    {draft.step === 7 && <section className="task"><h1>Best frames dekhein</h1>{selected && !draft.uncertain && <div className="face-grid">
      <figure className="face"><img src={selected.imageUrl} alt="Original selected face crop" /><figcaption>Original · {selected.timeLabel}</figcaption></figure>
      <figure className="face"><img src={selected.enhancedUrl} alt="Enhanced face crop for review" /><figcaption>Enhanced · review ke liye</figcaption></figure>
    </div>}
    {analysis && !draft.uncertain && trackFrames.length > 0 && <div className="guided-extra-clip guided-track-picture">
      <TrackFacePicture key={trackFrames.map((frame) => frame.id).join(',')} analysis={analysis} frames={trackFrames}
        onResult={(result) => setReviewPicture({ analysisId: analysis.id, trackId: trackFrames[0].trackId, result })} />
    </div>}
    <p>Quality score aur dikkat ek saath dekhein. Officer ka choice: {draft.uncertain ? 'Pakka nahi' : `Person ${selected?.trackId || ''}`}.</p>{candidates.length ? <div className="frame-list">{candidates.slice(0, 8).map((item) => <div className="frame-row" key={item.id}><img src={item.imageUrl} alt={`Face frame at ${item.timeLabel}`} /><div><strong>{item.timeLabel}</strong><span>Quality {Math.round(item.score)}/100</span><small>{item.flags.length ? item.flags.join(', ') : 'Koi quality warning nahi'}</small></div></div>)}</div> : <div className="notice">Koi face frame nahi mila. Report mein yeh baat likhi jayegi.</div>}<button className="primary" onClick={search}>Dusri clips mein dekhein →</button><Back onClick={() => go(6)} /></section>}
    {draft.step === 8 && <section className="task"><h1>Dusri clips mein dekhein</h1><p>Milta-julta chehra ek lead hai. Identity ka proof nahi.</p>{draft.uncertain ? <div className="notice">Person confirm nahi hua, isliye face search skip kiya gaya.</div> : busy ? <p>Search chal rahi hai…</p> : matches.length ? <div className="frame-list">{matches.slice(0, 8).map((item) => <div className="frame-row" key={item.id}><img src={item.imageUrl} alt="Possible match frame" /><div><strong>Possible match</strong><span>{item.filename}</span><small>{Math.round(item.similarity)}% milta-julta · {item.timeLabel}</small></div></div>)}</div> : <div className="notice">Abhi koi possible match nahi mila.</div>}<div className="guided-extra-clip">
      <h2>Dusri CCTV clip jodein</h2>
      <label>Camera channel<select value={extraCamera} onChange={(event) => setExtraCamera(event.target.value)} disabled={busy}>
        {['ATM-01', 'ATM-02', 'ATM-03', 'ATM-04'].map((channel) => <option key={channel}>{channel}</option>)}
      </select></label>
      <label>Nayi clip upload karein<input type="file" accept="video/*,.dav,.h264,.264,.asf,.ts,.m4v,.vob" disabled={busy}
        onChange={(event) => { upload(event.target.files?.[0], true); event.target.value = ''; }} /></label>
      {uploading && <div role="status">
        <p>{uploadPercent < 100 ? `Upload ${uploadPercent}%` : 'Video check ho raha hai…'}</p>
        <button type="button" className="secondary" onClick={() => uploadController.current?.abort()}>Wait rok dein</button>
      </div>}
      <label>Ya uploaded clip chunein<select value={extraClip?.id || ''} disabled={busy}
        onChange={(event) => { update({ extraClipId: event.target.value, extraAnalysisId: '' }); setExtraTime(''); setExtraAnalysis(null); }}>
        <option value="">Clip chunein</option>
        {clips.filter((item) => item.id !== draft.clipId).map((item) => <option key={item.id} value={item.id}>{item.filename}</option>)}
      </select></label>
      {extraClip && <form onSubmit={scanExtra}>
        <label>Dusri clip mein person ka video time (HH:MM:SS)
          <input required placeholder="00:02:15" pattern="[0-9]{2}:[0-5][0-9]:[0-5][0-9]" value={extraTime} onChange={(event) => setExtraTime(event.target.value)} />
        </label>
        <button className="secondary" type="submit" disabled={busy || scanningExtra}>Dusri clip scan karein</button>
      </form>}
      {scanningExtra && !error && <p role="status">Dusri clip scan ho rahi hai…</p>}
      {activeExtraAnalysis?.status === 'failed' && <p role="alert">{activeExtraAnalysis.error || 'Clip scan nahi ho saki.'}</p>}
      {activeExtraAnalysis?.status === 'completed' && <p role="status">
        {activeExtraAnalysis.candidates.some((crop) => crop.trackId > 0) ? 'Scan poori hui. Neeche face crops compare karein.' : 'Is time window mein tracked face crop nahi mila. Dusra video time try karein.'}
      </p>}
      {selected && <button className="secondary" type="button" disabled={busy} onClick={() => void run(async () => {
        const result = await api.search(selected.id);
        setMatches(result.matches);
      })}>Matches phir search karein</button>}
    </div>
    <div className="guided-extra-clip">
      {analysis && selected && selected.trackId > 0
        ? <CrossCameraFaceReview key={selected.id + ':' + (draft.extraAnalysisId || '') + ':' + (activeExtraAnalysis?.status || '')}
          analyses={[{ ...analysis, candidates: candidates.filter((crop) => crop.trackId === selected.trackId) }, ...(activeExtraAnalysis ? [activeExtraAnalysis] : [])]}
          initialCandidateId={selected.id} />
        : <><h2>Best face from 4–5 frames</h2><p>Pehli clip mein ek tracked face chunein.</p></>}
    </div>
    <button className="primary" onClick={() => go(9)}>Evidence sheet par jaayein →</button><Back onClick={() => go(7)} /></section>}
    {draft.step === 9 && <section className="task"><h1>Evidence sheet</h1><p>Download se pehle officer ka review check karein.</p><div className="summary"><div><span>Case</span><strong>{draft.caseNumber}</strong></div><div><span>ATM ID</span><strong>{draft.atmId}</strong></div><div><span>Video</span><strong>{clip?.filename || 'Missing'}</strong></div><div><span>Officer ka choice</span><strong>{draft.uncertain ? 'Pakka nahi' : selected ? `Person ${selected.trackId}` : 'Pending'}</strong></div></div><div className="notice">Yeh generated sheet local review record hai. Officer ko source video aur facts alag se verify karne honge.</div>{draft.reviewed && analysis?.status === 'completed' ? <a className="primary download" href={`/api/evidence/${analysis.id}.pdf`} download>Evidence sheet download karein ↓</a> : <p className="error">Officer review poora hone ke baad download milega.</p>}{reviewPicture && !draft.uncertain && reviewPicture.analysisId === analysis?.id && reviewPicture.trackId === selected?.trackId &&
      <div><a className="secondary" href={reviewPicture.result.imageUrl} download="drishti-final-face.png">Review picture PNG download karein</a></div>}
      <Back onClick={() => go(8)} /></section>}
  </main></div>{inspectedCandidate && <FrameInspector candidate={inspectedCandidate} clip={clips.find((item) => item.id === inspectedCandidate.clipId)} onClose={() => setInspectedCandidate(null)} />}{helpOpen && <div className="help-overlay" role="dialog" aria-modal="true" aria-label="Help and FAQ"><div className="help-dialog"><button className="help-close" onClick={() => setHelpOpen(false)} aria-label="Close help">×</button><h2>Madad chahiye?</h2><p>Har screen par sirf ek kaam karein. Pichhe jaane se saved case nahi mitta.</p><details><summary>DVR video nahi chal raha?</summary><p>DVR software mein MP4 (H.264) export karke phir upload karein. Original file apne paas rakhein.</p></details><details><summary>Bank aur CCTV time alag hain?</summary><p>Transaction screen par “Bank ka time” chunein aur CCTV video ka start time bhi dein.</p></details><details><summary>Chehra saaf nahi hai?</summary><p>“Pakka nahi” chunein. Galat identity confirm karne ki zaroorat nahi hai.</p></details><details><summary>Match ka matlab kya hai?</summary><p>“Possible match” sirf ek lead hai. Officer ko original videos khud dekhne honge.</p></details></div></div>}</div>;
}
function Back({ onClick }: { onClick: () => void }) { return <button className="back" onClick={onClick}>← Pichhe jaayein</button>; }
