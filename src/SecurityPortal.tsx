import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle, ArrowRight, BadgeCheck, Bell, Check, CheckCircle2, Clock3,
  Database, Eye, LoaderCircle, LockKeyhole, LogOut, Plus, Radio, RefreshCw,
  ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, UsersRound, X,
} from 'lucide-react';
import {
  AtmAssignment, PortalAlert, portalApi, PortalRole, PortalUser, RuleObservation, SecurityRule,
} from './portalApi';

type PortalTab = 'alerts' | 'guards' | 'routing';
type PortalToast = { kind: 'success' | 'error'; message: string } | null;

const ROLE_LABELS: Record<PortalRole, string> = {
  guard: 'On-Duty Guard (P1)',
  atm_admin: 'ATM Admin / Owner (P2)',
  govt_official: 'Govt / Police Official (P3)',
  super_admin: 'Command Super Admin',
};

function playSirenTone() {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(760, now);
    osc.frequency.linearRampToValueAtTime(1080, now + 0.25);
    osc.frequency.linearRampToValueAtTime(720, now + 0.5);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.56);
    window.setTimeout(() => { void ctx.close(); }, 700);
  } catch {
    /* Audio playback requires user interaction until unlocked */
  }
}

export default function SecurityPortal() {
  const [user, setUser] = useState<PortalUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<PortalToast>(null);

  useEffect(() => {
    let alive = true;
    void portalApi.me()
      .then((res) => { if (alive) setUser(res.user ?? null); })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false); });
    const expire = () => setUser(null);
    window.addEventListener('drishti-portal:session-expired', expire);
    return () => { alive = false; window.removeEventListener('drishti-portal:session-expired', expire); };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(t);
  }, [toast]);

  if (loading) {
    return (
      <div className="auth-loading">
        <div className="brand-emblem sec-emblem"><ShieldAlert size={22} /></div>
        <strong>DRISHTI SECURITY PORTAL</strong>
        <span>Connecting to Escalation Service…</span>
      </div>
    );
  }

  if (!user) {
    return <PortalAuthScreen onAuthenticated={setUser} onToast={setToast} toast={toast} />;
  }

  return (
    <PortalWorkspace
      user={user}
      onSignOut={async () => {
        try {
          await portalApi.logout();
        } catch {
          /* ignore expired session on sign-out */
        } finally {
          setUser(null);
        }
      }}
      toast={toast}
      onToast={setToast}
    />
  );
}

function PortalAuthScreen({ onAuthenticated, onToast, toast }: {
  onAuthenticated: (u: PortalUser) => void;
  onToast: (t: PortalToast) => void;
  toast: PortalToast;
}) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      const res = await portalApi.login(identifier, password);
      onAuthenticated(res.user);
    } catch (error) {
      setErr(error instanceof Error ? error.message : 'Login failed.');
    } finally {
      setBusy(false);
    }
  };


  return (
    <main className="auth-screen">
      <div className="auth-side-art sec-side-art">
        <div className="auth-brand">
          <div className="brand-emblem sec-emblem"><ShieldAlert size={22} /></div>
          <div><strong>SECURITY &amp; ESCALATION PORTAL</strong><span>GUARD · ATM ADMIN · GOVT RESPONSE TIER</span></div>
        </div>
        <div className="auth-art-copy">
          <span className="auth-kicker"><Radio size={15} /> API-BRIDGED TO DRISHTI AI (:8100)</span>
          <h1>Observe context first.<br /><em>Escalate real threats.</em></h1>
          <p>Rule 1 logs helmet/mask entries silently. Only genuine machine tampering triggers sirens across Priority 1 (Guard) → Priority 2 (ATM Admin) → Priority 3 (Backup Govt Official).</p>
        </div>
        <div className="auth-art-foot">
          <a className="sec-back-link" href="/"><LockKeyhole size={14} /> Return to Drishti PS04 AI Console</a>
        </div>
      </div>

      <section className="auth-panel">
        <div className="auth-card">
          <span className="auth-kicker">ROLE-BASED COMMAND SIGN-IN</span>
          <h2>Guard &amp; Official Portal</h2>
          <p className="auth-description">Sign in with an account provisioned by your organization’s portal administrator.</p>

          {err && <div className="auth-error" role="alert"><AlertCircle size={17} />{err}</div>}

          <form className="auth-form" onSubmit={(e) => void submitPassword(e)}>
            <label htmlFor="sec-ident">Employee ID or email
              <input id="sec-ident" name="identifier" autoComplete="username" required value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
            </label>
            <label htmlFor="sec-pass">Passphrase
              <input id="sec-pass" name="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button className="button button-primary auth-submit" type="submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={16} /> : <LockKeyhole size={16} />} Sign in to Security Portal <ArrowRight size={16} />
            </button>
          </form>

          <div className="auth-switch">
            <a href="/">← Back to Drishti AI</a>
          </div>
        </div>
      </section>
      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span><CheckCircle2 size={17} /></span><p>{toast.message}</p><button onClick={() => onToast(null)}><X size={16} /></button></div>}
    </main>
  );
}

function PortalWorkspace({ user, onSignOut, toast, onToast }: {
  user: PortalUser;
  onSignOut: () => Promise<void>;
  toast: PortalToast;
  onToast: (t: PortalToast) => void;
}) {
  const [tab, setTab] = useState<PortalTab>('alerts');
  const [alerts, setAlerts] = useState<PortalAlert[]>([]);
  const [observations, setObservations] = useState<RuleObservation[]>([]);
  const [guards, setGuards] = useState<PortalUser[]>([]);
  const [assignments, setAssignments] = useState<AtmAssignment[]>([]);
  const [rules, setRules] = useState<SecurityRule[]>([]);
  const [sirenMuted, setSirenMuted] = useState(false);
  const [nowMs, setNowMs] = useState(Date.now());
  const [newGuardOpen, setNewGuardOpen] = useState(false);
  const lastSirenAlertRef = useRef<string>('');
  const pollBusyRef = useRef(false);

  const loadAll = useCallback(async () => {
    if (pollBusyRef.current) return;
    pollBusyRef.current = true;
    try {
      const [alertRes, guardList, assignList, ruleList] = await Promise.all([
        portalApi.alerts(),
        portalApi.guards(),
        portalApi.assignments(),
        portalApi.rules(),
      ]);
      setAlerts(alertRes.alerts);
      setObservations(alertRes.observations);
      setGuards(guardList);
      setAssignments(assignList);
      setRules(ruleList);
    } catch (e) {
      onToast({ kind: 'error', message: e instanceof Error ? e.message : 'Sync failed.' });
    } finally {
      pollBusyRef.current = false;
    }
  }, [onToast]);

  useEffect(() => {
    void loadAll();
    const poll = window.setInterval(() => void loadAll(), 3000);
    const clock = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => { window.clearInterval(poll); window.clearInterval(clock); };
  }, [loadAll]);

  const activeUrgentAlert = useMemo(() => {
    return alerts.find((a) => {
      if (a.status === 'resolved' || a.status === 'acknowledged') return false;
      if (!a.sirenActive) return false;
      if (a.incidentKind === 'stream.camera_tamper') return true;
      if (user.role === 'super_admin') return true;
      if (user.role === 'guard' && a.currentPriority === 1) return true;
      if (user.role === 'atm_admin' && a.currentPriority >= 2) return true;
      if (user.role === 'govt_official' && a.currentPriority >= 2) return true;
      return false;
    });
  }, [alerts, user.role]);

  useEffect(() => {
    if (activeUrgentAlert && !sirenMuted && lastSirenAlertRef.current !== `${activeUrgentAlert.id}:${activeUrgentAlert.currentPriority}`) {
      lastSirenAlertRef.current = `${activeUrgentAlert.id}:${activeUrgentAlert.currentPriority}`;
      playSirenTone();
    }
  }, [activeUrgentAlert, sirenMuted]);

  const simulateBreach = async () => {
    const targetAtm = user.assignedAtms[0] || 'ATM-01';
    try {
      const simRes = await portalApi.simulateBreach(targetAtm, true);
      if (!sirenMuted) playSirenTone();
      if (simRes.action === 'deduplicated') {
        onToast({ kind: 'success', message: `Open breach alert already active for ${targetAtm} (deduplicated) — acknowledge or resolve it to trigger a fresh siren.` });
      } else {
        onToast({ kind: 'success', message: `Simulated Rule 1 (Helmet Entry) → Rule 2 (Machine Shake) → Guard Priority 1 Siren on ${targetAtm}!` });
      }
      await loadAll();
    } catch (e) {
      onToast({ kind: 'error', message: e instanceof Error ? e.message : 'Simulation failed.' });
    }
  };

  const actAlert = async (id: string, action: 'acknowledge' | 'escalate' | 'resolve') => {
    try {
      if (action === 'acknowledge') await portalApi.acknowledgeAlert(id);
      else if (action === 'escalate') await portalApi.escalateAlert(id);
      else await portalApi.resolveAlert(id);
      onToast({ kind: 'success', message: `Alert ${action}d cleanly.` });
      await loadAll();
    } catch (e) {
      onToast({ kind: 'error', message: e instanceof Error ? e.message : 'Action failed.' });
    }
  };

  const canManage = user.role === 'atm_admin' || user.role === 'super_admin';
  const activeCount = alerts.filter((a) => a.status !== 'resolved').length;

  return (
    <div className="app-shell">
      <header className="top-nav-shell sec-nav-shell">
        <div className="top-nav-inner">
          <div className="top-utility-row">
            <div className="brand-lockup">
              <div className="brand-emblem sec-emblem"><ShieldAlert size={21} /></div>
              <div>
                <strong>DRISHTI · SECURITY &amp; ESCALATION PORTAL</strong>
                <span>{ROLE_LABELS[user.role]} · API BRIDGED TO DRISHTI AI</span>
              </div>
            </div>
            <div className="top-utility-right">
              <button
                className={`button button-compact ${sirenMuted ? 'button-outline' : 'button-primary'}`}
                onClick={() => { setSirenMuted((v) => !v); if (sirenMuted) playSirenTone(); }}
                title="Toggle live security siren"
              >
                <Bell size={14} /> {sirenMuted ? 'Siren Muted' : 'Siren Armed'}
              </button>
              <a className="button button-outline button-compact" href="/"><Eye size={14} /> Drishti AI ↗</a>
              <div className="profile-pill">
                <div className="profile-avatar sec-avatar">{user.displayName.slice(0, 2).toUpperCase()}</div>
                <div className="profile-copy"><strong>{user.displayName}</strong><span>{user.employeeId}</span></div>
              </div>
              <button className="icon-button" aria-label="Sign out" onClick={() => void onSignOut()}><LogOut size={18} /></button>
            </div>
          </div>

          <div className="top-tabs-row">
            <nav className="main-nav" aria-label="Security Portal Navigation">
              <button className={`nav-item ${tab === 'alerts' ? 'nav-active' : ''}`} onClick={() => setTab('alerts')}>
                <ShieldAlert size={15} /><span>Escalation &amp; Siren</span>{activeCount > 0 && <small>{activeCount}</small>}
              </button>
              <button className={`nav-item ${tab === 'guards' ? 'nav-active' : ''}`} onClick={() => setTab('guards')}>
                <UsersRound size={15} /><span>Guards &amp; eKYC</span><small>{guards.length}</small>
              </button>
              {canManage && (
                <button className={`nav-item ${tab === 'routing' ? 'nav-active' : ''}`} onClick={() => setTab('routing')}>
                  <SlidersHorizontal size={15} /><span>Rules &amp; Escalation Matrix</span>
                </button>
              )}
            </nav>
            <div className="nav-vault-pill"><LockKeyhole size={14} /> Priority Flow: Guard (P1) → ATM Admin (P2) → Backup Govt (P3)</div>
          </div>
        </div>
      </header>

      <main className="main-column">
        <div className="page-wrap">
          {activeUrgentAlert && (
            <div className="sec-siren-banner" role="alert">
              <div className="sec-siren-left">
                <ShieldAlert size={22} />
                <div>
                  <strong>PRIORITY {activeUrgentAlert.currentPriority} SIREN ALERT · {activeUrgentAlert.atmId}</strong>
                  <span>{activeUrgentAlert.summary}</span>
                </div>
              </div>
              <div className="stream-actions-row">
                <button className="button button-primary button-compact" onClick={() => void actAlert(activeUrgentAlert.id, 'acknowledge')}>
                  <Check size={14} /> Silence Siren &amp; Acknowledge
                </button>
                <button className="button button-outline button-compact" style={{ background: '#fff' }} onClick={() => void actAlert(activeUrgentAlert.id, 'escalate')}>
                  Escalate Tier
                </button>
              </div>
            </div>
          )}

          {tab === 'alerts' && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Priority Escalation &amp; Rule Engine</h1>
                  <p>Alerts trigger only after Rule-1 monitoring detects genuine machine tampering, shaking, breaking, or force breach.</p>
                </div>
                <div className="page-actions">
                  <button className="button button-primary button-compact" onClick={() => void simulateBreach()}>
                    <Sparkles size={14} /> Simulate 2-Stage ATM Breach
                  </button>
                  <button className="button button-outline button-compact" onClick={() => void loadAll()}>
                    <RefreshCw size={14} /> Refresh
                  </button>
                </div>
              </div>

              <div className="sec-split-grid">
                <section className="panel telemetry-panel">
                  <SectionHead title="Active &amp; Escalated Incidents" detail={`${alerts.length} recorded incident(s) routed via priority tiers`} />
                  {alerts.length ? (
                    <div className="sec-alert-list">
                      {alerts.map((al) => {
                        const remSec = al.escalateAfterAt ? Math.max(0, Math.ceil((new Date(al.escalateAfterAt).getTime() - nowMs) / 1000)) : 0;
                        return (
                          <article className={`sec-alert-card sec-alert-${al.status}`} key={al.id}>
                            <div className="sec-alert-top">
                              <span className={`sec-prio-pill prio-${al.currentPriority}`}>
                                PRIORITY {al.currentPriority} · {al.status.replace('_', ' ').toUpperCase()}
                              </span>
                              <span className="camera-id-pill">{al.atmId}</span>
                              {al.priorRuleCode && <span className="sec-rule-link">Linked: {al.priorRuleCode}</span>}
                              {remSec > 0 && (
                                <span className="sec-sla-timer"><Clock3 size={12} /> Auto-escalates in {remSec}s</span>
                              )}
                            </div>

                            <strong className="sec-alert-title">{al.summary}</strong>

                            <div className="sec-ladder">
                              <span className={al.currentPriority >= 1 ? 'ladder-active' : ''}>1. Guard: {al.assignedGuardName}</span>
                              <ArrowRight size={13} />
                              <span className={al.currentPriority >= 2 ? 'ladder-active' : ''}>2. ATM Admin: {al.assignedAdminName}</span>
                              <ArrowRight size={13} />
                              <span className={al.currentPriority >= 3 ? 'ladder-active' : ''}>3. Backup Govt: {al.backupGovtName}</span>
                            </div>

                            {al.snapshotUrl && (
                              <img className="sec-alert-snap" src={al.snapshotUrl} alt={`Incident ${al.atmId}`} />
                            )}

                            <div className="sec-timeline">
                              {al.timeline.map((step, i) => (
                                <small key={i}>• <b>{step.tier}</b>: {step.note} ({new Date(step.at).toLocaleTimeString('en-IN')})</small>
                              ))}
                            </div>

                            {al.status !== 'resolved' && (
                              <div className="stream-actions-row">
                                {al.status !== 'acknowledged' && (
                                  <button className="button button-primary button-compact" onClick={() => void actAlert(al.id, 'acknowledge')}>
                                    <Check size={13} /> Acknowledge
                                  </button>
                                )}
                                {al.currentPriority < 3 && (
                                  <button className="button button-outline button-compact" onClick={() => void actAlert(al.id, 'escalate')}>
                                    Escalate to P{al.currentPriority + 1}
                                  </button>
                                )}
                                <button className="button button-outline button-compact" onClick={() => void actAlert(al.id, 'resolve')}>
                                  Mark Resolved
                                </button>
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="empty-line"><span><ShieldCheck size={18} /></span><div><strong>All ATMs clear</strong><p>When Rule 2 tampering/force breach follows Rule 1 observation, alerts escalate here immediately.</p></div></div>
                  )}
                </section>

                <aside className="review-side-stack">
                  <section className="panel telemetry-panel">
                    <SectionHead title="Stage 1: Silent Observations (Rule 1)" detail="Logged without triggering siren (helmet / mask / cap entry)" />
                    {observations.length ? (
                      <div className="activity-list">
                        {observations.slice(0, 12).map((obs) => (
                          <div className="activity-item" key={obs.id}>
                            <span className={`activity-pin ${obs.status === 'escalated' ? 'pin-amber' : ''}`} />
                            <div>
                              <strong>{obs.atmId} · {obs.ruleCode} ({obs.status})</strong>
                              <time>{obs.detail} · {new Date(obs.observedAt).toLocaleTimeString('en-IN')}</time>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="empty-line"><span><Eye size={18} /></span><div><strong>No Rule 1 observations yet</strong><p>Masked/helmeted entries log silently here for context building without false sirens.</p></div></div>
                    )}
                  </section>
                </aside>
              </div>
            </>
          )}

          {tab === 'guards' && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Guard Profiles &amp; Aadhaar-Style eKYC Verification</h1>
                  <p>Minimum-data guard profiles: raw 12-digit Aadhaar numbers are never stored (only masked XXXX-XXXX-last4 + HMAC verification ref).</p>
                </div>
                {canManage && (
                  <button className="button button-primary button-compact" onClick={() => setNewGuardOpen(true)}>
                    <Plus size={15} /> Register Guard / Official
                  </button>
                )}
              </div>

              <div className="sec-guard-grid">
                {guards.map((g) => (
                  <article className="panel sec-guard-card" key={g.id}>
                    <div className="sec-guard-head">
                      <div className="profile-avatar sec-avatar">{g.displayName.slice(0, 2).toUpperCase()}</div>
                      <div>
                        <strong>{g.displayName}</strong>
                        <span>{g.employeeId} · {ROLE_LABELS[g.role]}</span>
                      </div>
                      <span className={`account-status account-${g.verificationStatus === 'verified' ? 'active' : 'pending'}`}>
                        {g.verificationStatus}
                      </span>
                    </div>

                    <div className="sec-guard-meta">
                      <div><small>Mobile</small><span>{g.mobile || '—'}</span></div>
                      <div><small>Duty Timings</small><span>{g.dutyTiming}</span></div>
                      <div><small>Assigned ATMs</small><span>{g.assignedAtms.join(', ') || 'None'}</span></div>
                      <div><small>Emergency Contact</small><span>{g.emergencyContact || '—'}</span></div>
                      <div><small>Address &amp; PIN</small><span>{g.address || '—'} ({g.pinCode || '—'})</span></div>
                      <div><small>Identity check</small><span>{g.verificationStatus === 'verified' ? 'Marked verified by portal administrator' : 'Not verified'}</span></div>
                    </div>

                    <div className="stream-actions-row">
                      {canManage && g.verificationStatus !== 'verified' && (
                        <button
                          className="button button-primary button-compact"
                          onClick={async () => {
                            try {
                              await portalApi.updateGuard(g.id, { verification_status: 'verified' });
                              onToast({ kind: 'success', message: `${g.displayName} marked verified.` });
                              await loadAll();
                            } catch (e) {
                              onToast({ kind: 'error', message: e instanceof Error ? e.message : 'Guard approval failed.' });
                            }
                          }}
                        >
                          <BadgeCheck size={14} /> Approve Guard
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}

          {tab === 'routing' && canManage && (
            <div className="sec-split-grid">
              <section className="panel telemetry-panel">
                <SectionHead title="ATM Priority Escalation Chain" detail="Assign Guard (P1) → ATM Admin (P2) → Backup Govt Official (P3) per ATM" />
                <div className="table-scroll">
                  <table className="data-table">
                    <thead><tr><th>ATM</th><th>P1 GUARD</th><th>P2 ATM ADMIN</th><th>P3 BACKUP GOVT</th><th>SLA (s)</th><th /></tr></thead>
                    <tbody>
                      {assignments.map((a) => (
                        <AssignmentRow
                          key={a.atmId}
                          row={a}
                          personnel={guards}
                          onSaved={() => { onToast({ kind: 'success', message: `Saved escalation chain for ${a.atmId}` }); void loadAll(); }}
                          onError={(msg) => onToast({ kind: 'error', message: msg })}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel telemetry-panel">
                <SectionHead title="Contextual Security Rules" detail="Control Stage-1 silent monitoring vs Stage-2 escalation alerts" />
                {rules.map((r) => (
                  <div className="sec-rule-row" key={r.id}>
                    <div>
                      <strong>{r.name}</strong>
                      <small>{r.description}</small>
                    </div>
                    <button
                      className={`button button-compact ${r.enabled ? 'button-primary' : 'button-outline'}`}
                      onClick={async () => {
                        try {
                          await portalApi.toggleRule(r.id, !r.enabled);
                          await loadAll();
                        } catch (e) {
                          onToast({ kind: 'error', message: e instanceof Error ? e.message : 'Could not update rule.' });
                        }
                      }}
                    >
                      {r.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </div>
                ))}
              </section>
            </div>
          )}
        </div>
      </main>

      {newGuardOpen && (
        <NewGuardModal
          canCreateOfficials={user.role === 'super_admin'}
          onClose={() => setNewGuardOpen(false)}
          onCreated={() => { setNewGuardOpen(false); onToast({ kind: 'success', message: 'Personnel account created.' }); void loadAll(); }}
          onError={(msg) => onToast({ kind: 'error', message: msg })}
        />
      )}

      {toast && <div className={`toast toast-${toast.kind}`} role="status"><span><CheckCircle2 size={17} /></span><p>{toast.message}</p><button onClick={() => onToast(null)}><X size={16} /></button></div>}
    </div>
  );
}

function SectionHead({ title, detail }: { title: string; detail: string }) {
  return <div className="section-title"><div><h2>{title}</h2><p>{detail}</p></div></div>;
}

function AssignmentRow({ row, personnel, onSaved, onError }: {
  row: AtmAssignment;
  personnel: PortalUser[];
  onSaved: () => void;
  onError: (msg: string) => void;
}) {
  const [guardId, setGuardId] = useState(row.guardUserId);
  const [adminId, setAdminId] = useState(row.adminUserId);
  const [backupId, setBackupId] = useState(row.backupGovtUserId);
  const [sla, setSla] = useState(row.p1SlaSeconds);
  useEffect(() => {
    setGuardId(row.guardUserId);
    setAdminId(row.adminUserId);
    setBackupId(row.backupGovtUserId);
    setSla(row.p1SlaSeconds);
  }, [row.guardUserId, row.adminUserId, row.backupGovtUserId, row.p1SlaSeconds]);
  const guardsOnly = personnel.filter((p) => p.role === 'guard');
  const adminsOnly = personnel.filter((p) => p.role === 'atm_admin' || p.role === 'super_admin');
  const govtOnly = personnel.filter((p) => p.role === 'govt_official' || p.role === 'super_admin');

  return (
    <tr>
      <td><strong>{row.atmId}</strong><span>{row.atmName}</span></td>
      <td>
        <select id={`assign-guard-${row.atmId}`} name={`guard_${row.atmId}`} aria-label={`Priority 1 Guard for ${row.atmId}`} value={guardId} onChange={(e) => setGuardId(e.target.value)}>
          <option value="">Unassigned</option>
          {guardsOnly.map((g) => <option key={g.id} value={g.id}>{g.displayName}</option>)}
        </select>
      </td>
      <td>
        <select id={`assign-admin-${row.atmId}`} name={`admin_${row.atmId}`} aria-label={`Priority 2 ATM Admin for ${row.atmId}`} value={adminId} onChange={(e) => setAdminId(e.target.value)}>
          <option value="">Unassigned</option>
          {adminsOnly.map((a) => <option key={a.id} value={a.id}>{a.displayName}</option>)}
        </select>
      </td>
      <td>
        <select id={`assign-backup-${row.atmId}`} name={`backup_${row.atmId}`} aria-label={`Priority 3 Backup Govt Official for ${row.atmId}`} value={backupId} onChange={(e) => setBackupId(e.target.value)}>
          <option value="">Unassigned</option>
          {govtOnly.map((g) => <option key={g.id} value={g.id}>{g.displayName}</option>)}
        </select>
      </td>
      <td><input id={`assign-sla-${row.atmId}`} name={`sla_${row.atmId}`} aria-label={`SLA seconds for ${row.atmId}`} type="number" min={5} max={300} value={sla} onChange={(e) => setSla(Number(e.target.value) || 20)} style={{ width: 64 }} /></td>
      <td>
        <button
          className="button button-outline button-compact"
          onClick={async () => {
            try {
              await portalApi.updateAssignment(row.atmId, {
                guard_user_id: guardId,
                admin_user_id: adminId,
                govt_user_id: row.govtUserId || backupId,
                backup_govt_user_id: backupId,
                p1_sla_seconds: sla,
                p2_sla_seconds: sla,
              });
              onSaved();
            } catch (e) {
              onError(e instanceof Error ? e.message : `Failed to save escalation chain for ${row.atmId}.`);
            }
          }}
        >
          Save
        </button>
      </td>
    </tr>
  );
}

function NewGuardModal({ canCreateOfficials, onClose, onCreated, onError }: {
  canCreateOfficials: boolean;
  onClose: () => void;
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [empId, setEmpId] = useState('EMP-GRD-103');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('+91-98290-');
  const [role, setRole] = useState<PortalRole>('guard');
  const [password, setPassword] = useState('');
  const [address, setAddress] = useState('');
  const [pinCode, setPinCode] = useState('302001');
  const [atms, setAtms] = useState('ATM-01, ATM-02');
  const [duty, setDuty] = useState('08:00 - 20:00');
  const [emergency, setEmergency] = useState('+91-');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await portalApi.createGuard({
        employee_id: empId,
        email,
        display_name: name,
        mobile,
        role,
        password,
        address,
        pin_code: pinCode,
        assigned_atms: atms.split(',').map((s) => s.trim()).filter(Boolean),
        duty_timing: duty,
        emergency_contact: emergency,
      });
      onCreated();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to create personnel record.');
    }
  };

  return (
    <div className="privacy-modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="privacy-modal slot-modal" onClick={(e) => e.stopPropagation()}>
        <div className="section-title">
          <div><h2>Register Security Personnel</h2><p>Add guard, ATM Admin, or Government Official profile</p></div>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={(e) => void submit(e)}>
          <div className="dossier-grid">
            <input id="new-guard-emp-id" name="employee_id" aria-label="Employee or Guard ID" autoComplete="username" required placeholder="Employee / Guard ID" value={empId} onChange={(e) => setEmpId(e.target.value)} />
            <input id="new-guard-name" name="display_name" aria-label="Full Name" autoComplete="name" required placeholder="Full Name" value={name} onChange={(e) => setName(e.target.value)} />
            <input id="new-guard-email" name="email" aria-label="Work Email" autoComplete="email" required type="email" placeholder="Work Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input id="new-guard-mobile" name="mobile" aria-label="Mobile Number" autoComplete="tel" required placeholder="Mobile Number" value={mobile} onChange={(e) => setMobile(e.target.value)} />
            <input id="new-guard-address" name="address" aria-label="Address" autoComplete="street-address" placeholder="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
            <input id="new-guard-pin" name="pin_code" aria-label="PIN Code" autoComplete="postal-code" placeholder="PIN Code" value={pinCode} onChange={(e) => setPinCode(e.target.value)} />
            <input id="new-guard-atms" name="assigned_atms" aria-label="Assigned ATMs" placeholder="Assigned ATMs (comma separated)" value={atms} onChange={(e) => setAtms(e.target.value)} />
            <input id="new-guard-duty" name="duty_timing" aria-label="Duty Timing" placeholder="Duty Timing" value={duty} onChange={(e) => setDuty(e.target.value)} />
            <input id="new-guard-emergency" name="emergency_contact" aria-label="Emergency Contact" autoComplete="tel" placeholder="Emergency Contact" value={emergency} onChange={(e) => setEmergency(e.target.value)} />
            <select id="new-guard-role" name="role" aria-label="Portal Role" value={role} onChange={(e) => setRole(e.target.value as PortalRole)}>
              <option value="guard">Guard</option>
              <option value="atm_admin">ATM Admin / Owner</option>
              {canCreateOfficials && <option value="govt_official">Government Official</option>}
              {canCreateOfficials && <option value="super_admin">Super Admin</option>}
            </select>
            <input id="new-guard-password" name="password" aria-label="Passphrase" autoComplete="new-password" required minLength={8} type="password" placeholder="Passphrase (8+ chars)" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="button button-primary button-compact" type="submit"><Database size={14} /> Save Record</button>
          </div>
        </form>
      </div>
    </div>
  );
}
