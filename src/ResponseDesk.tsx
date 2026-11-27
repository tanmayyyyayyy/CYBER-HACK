import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, ArrowDownToLine, Check, CheckCircle2, Clock3, FileText, Printer, RotateCcw, ShieldAlert, UserRoundCheck } from 'lucide-react';
import { Analysis, AuditIntegrity, AuditItem, AuthUser, Clip } from './api';

type View = 'response' | 'handoff' | 'custody';
type Stage = 'received' | 'acknowledged' | 'info_requested' | 'escalated' | 'resolved' | 'false_alarm';
type DemoLog = { id: string; at: string; action: string; by: string; detail: string };
type DemoState = { stage: Stage; owner: string; note: string; log: DemoLog[] };

const STORAGE_KEY = 'drishti-response-desk-demo-v1';
const initialLog: DemoLog = [{ id: 'received', at: '2026-06-18T10:42:16+05:30', action: 'Simulated alert received', by: 'DEMO SYSTEM', detail: 'Fictional ATM-04 · door-open sensor scenario · no responder notified.' }];
const initialState: DemoState = { stage: 'received', owner: '', note: '', log: initialLog };
const stageLabel: Record<Stage, string> = {
  received: 'New · awaiting review', acknowledged: 'Acknowledged', info_requested: 'More information requested',
  escalated: 'Escalated for review', resolved: 'Resolved by reviewer', false_alarm: 'Marked as false alarm',
};

function loadState(): DemoState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return initialState;
    const value = JSON.parse(raw) as DemoState;
    if (!['received', 'acknowledged', 'info_requested', 'escalated', 'resolved', 'false_alarm'].includes(value.stage) || !Array.isArray(value.log)) return initialState;
    return value;
  } catch { return initialState; }
}

function stamp() { return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date()); }
function safeFilePart(value: string) { return value.replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '').slice(0, 40) || 'case'; }

export default function ResponseDesk({ user, clips, analyses, audit, auditIntegrity, onReview }: {
  user: AuthUser; clips: Clip[]; analyses: Analysis[]; audit: AuditItem[]; auditIntegrity: AuditIntegrity | null; onReview: (id: string) => void;
}) {
  const [view, setView] = useState<View>('response');
  const [demo, setDemo] = useState<DemoState>(loadState);
  const [analysisId, setAnalysisId] = useState('');
  const [noteInput, setNoteInput] = useState('');
  const selectedAnalysis = useMemo(() => {
    const selected = analyses.find((analysis) => analysis.id === analysisId);
    return selected || analyses.find((analysis) => analysis.status === 'completed') || analyses[0];
  }, [analyses, analysisId]);
  const selectedClip = clips.find((clip) => clip.id === selectedAnalysis?.clipId);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, JSON.stringify(demo)); }, [demo]);

  const record = (action: string, detail: string, change: Partial<DemoState> = {}) => {
    const entry: DemoLog = { id: crypto.randomUUID(), at: new Date().toISOString(), action, by: user.displayName, detail };
    setDemo((current) => ({ ...current, ...change, log: [entry, ...current.log] }));
  };

  const resetDemo = () => {
    if (!window.confirm('Reset the fictional response scenario and its browser-local demo history?')) return;
    localStorage.removeItem(STORAGE_KEY);
    setDemo(initialState);
  };

  const packet = useMemo(() => {
    if (!selectedAnalysis) return null;
    return {
      schema: 'drishti.demonstration-handoff.v1',
      notice: 'SIMULATION ONLY — not an official report, dispatch, or chain-of-custody record.',
      preparedAt: new Date().toISOString(),
      case: { reference: selectedAnalysis.caseRef || 'UNASSIGNED CASE', transactionReference: selectedAnalysis.transactionRef, transactionTime: selectedAnalysis.transactionTime },
      review: {
        analysisId: selectedAnalysis.id, analysisStatus: selectedAnalysis.status,
        summary: selectedAnalysis.status === 'completed' ? `${selectedAnalysis.candidates.length} candidate frame(s) surfaced for human review.` : `Analysis status: ${selectedAnalysis.status}.`,
        candidateCounts: {
          total: selectedAnalysis.candidates.length,
          selected: selectedAnalysis.candidates.filter((candidate) => candidate.reviewStatus === 'selected').length,
          rejected: selectedAnalysis.candidates.filter((candidate) => candidate.reviewStatus === 'rejected').length,
          awaitingReview: selectedAnalysis.candidates.filter((candidate) => candidate.reviewStatus === 'unreviewed').length,
        },
      },
      evidence: selectedClip ? [{
        clipId: selectedClip.id, filename: selectedClip.filename, camera: selectedClip.cameraId,
        uploadedAt: selectedClip.uploadedAt, sha256: selectedClip.sha256,
        note: 'Metadata reference only. Video and candidate images are not included in this handoff preview.',
      }] : [],
      audit: { localChainVerified: auditIntegrity?.verified ?? false, entriesChecked: auditIntegrity?.entriesChecked ?? 0, headHash: auditIntegrity?.headHash ?? null, limitation: 'Local workspace audit status is reported for context only; this packet is not independently signed or custody-certified.' },
      responseSimulation: { scenario: 'Fictional ATM-04 sensor event', status: stageLabel[demo.stage], assignedTo: demo.owner || null, entries: demo.log },
    };
  }, [selectedAnalysis, selectedClip, auditIntegrity, demo]);

  const downloadPacket = () => {
    if (!packet) return;
    const blob = new Blob([JSON.stringify(packet, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `demo-handoff-${safeFilePart(packet.case.reference)}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const terminal = demo.stage === 'resolved' || demo.stage === 'false_alarm';

  return <div className="response-desk">
    <div className="response-sim-banner"><AlertTriangle size={18} /><div><strong>SIMULATION · NO AUTHORITY OR RESPONDER HAS BEEN CONTACTED</strong><span>All response actions below are demonstration-only and are saved in this browser. They do not send messages or change case evidence.</span></div><button className="response-reset" onClick={resetDemo}><RotateCcw size={14} /> Reset demo</button></div>

    <div className="response-tabs" role="group" aria-label="Authority response desk sections">
      <button aria-pressed={view === 'response'} className={view === 'response' ? 'active' : ''} onClick={() => setView('response')}><ShieldAlert size={15} /> Response queue</button>
      <button aria-pressed={view === 'handoff'} className={view === 'handoff' ? 'active' : ''} onClick={() => setView('handoff')}><FileText size={15} /> Handoff packet</button>
      <button aria-pressed={view === 'custody'} className={view === 'custody' ? 'active' : ''} onClick={() => setView('custody')}><Clock3 size={15} /> Activity timeline</button>
    </div>

    {view === 'response' && <>
      <div className="response-overview"><div><span className="response-eyebrow">FICTIONAL TRAINING SCENARIO · JAIPUR</span><h2>Authority Response Desk</h2><p>Illustrates how a reviewed alert could be acknowledged, assigned, and closed by an authorized team.</p></div><div className="response-status-card"><span className="response-live-dot" /><div><strong>DEMO EVENT</strong><span>18 JUN 2026 · 10:42 IST</span></div></div></div>
      <div className="response-grid">
        <section className="response-panel response-queue">
          <div className="response-panel-head"><div><span className="response-eyebrow">INCOMING · SIMULATED</span><h3>ATM-04 · Access door sensor</h3></div><span className={`response-stage stage-${demo.stage}`}>{stageLabel[demo.stage]}</span></div>
          <div className="response-facts"><div><span>Alert reference</span><strong>DR-DEMO-042</strong></div><div><span>Location</span><strong>Fictional Jaipur branch</strong></div><div><span>Source</span><strong>Simulated sensor event</strong></div><div><span>Priority</span><strong className="priority-demo">P1 · DEMO ONLY</strong></div></div>
          <div className="response-description"><Activity size={17} /><p>A fictional access-door event is shown for workflow demonstration. No camera trigger, dispatch connection, or real incident is involved.</p></div>
          <div className="response-actions">
            {!terminal && demo.stage === 'received' && <button className="response-primary" onClick={() => record('Alert acknowledged', 'Reviewer acknowledged the simulated alert.', { stage: 'acknowledged', owner: user.displayName })}><Check size={15} /> Acknowledge & take ownership</button>}
            {!terminal && demo.stage !== 'received' && <button className="response-primary" onClick={() => record('More information requested', 'A request was recorded in the local simulation only.', { stage: 'info_requested' })}>Request more information</button>}
            {!terminal && <button className="response-secondary" onClick={() => record('Escalated for review', 'Escalation recorded in the local simulation only.', { stage: 'escalated', owner: demo.owner || user.displayName })}><ArrowDownToLine size={15} /> Escalate for review</button>}
            {!terminal && <button className="response-secondary" onClick={() => record('Marked as false alarm', 'Reviewer marked the fictional event as a false alarm.', { stage: 'false_alarm' })}>Mark false alarm</button>}
            {!terminal && demo.stage !== 'received' && <button className="response-secondary" onClick={() => record('Alert resolved', 'Reviewer closed the simulated workflow.', { stage: 'resolved' })}><CheckCircle2 size={15} /> Resolve</button>}
          </div>
        </section>
        <section className="response-panel response-owner-panel">
          <span className="response-eyebrow">REVIEWER WORKSPACE</span><h3><UserRoundCheck size={18} /> Assignment & note</h3>
          <div className="response-owner"><span>Current owner</span><strong>{demo.owner || 'Unassigned'}</strong></div>
          <label htmlFor="response-note">Internal demonstration note</label><textarea id="response-note" value={noteInput} maxLength={500} onChange={(event) => setNoteInput(event.target.value)} placeholder="Add a short simulated handoff note…" />
          <button className="response-secondary response-note-button" disabled={!noteInput.trim()} onClick={() => { record('Reviewer note added', noteInput.trim(), { note: noteInput.trim() }); setNoteInput(''); }}>Add note to demo timeline</button>
          {demo.note && <p className="response-last-note"><strong>Latest note</strong>{demo.note}</p>}
        </section>
      </div>
      <div className="response-bottom-note"><ShieldAlert size={16} /><span>This screen demonstrates a possible operator workflow. The current prototype has no verified authority accounts, live dispatch integration, or delivery acknowledgements.</span></div>
    </>}

    {view === 'handoff' && <>
      <div className="response-overview"><div><span className="response-eyebrow">REVIEWER PREPARED · DRAFT</span><h2>Evidence handoff packet</h2><p>Creates a reviewable metadata summary from an existing local analysis. Video files are not attached.</p></div><div className="response-packet-actions"><button className="response-secondary" onClick={() => window.print()}><Printer size={15} /> Print preview</button><button className="response-primary" disabled={!packet} onClick={downloadPacket}><ArrowDownToLine size={15} /> Download JSON</button></div></div>
      <section className="response-panel handoff-select"><label htmlFor="handoff-analysis">Select local analysis</label><select id="handoff-analysis" value={selectedAnalysis?.id || ''} onChange={(event) => setAnalysisId(event.target.value)}><option value="" disabled>{analyses.length ? 'Choose analysis' : 'No analyses available — load the demo case first'}</option>{analyses.map((analysis) => <option key={analysis.id} value={analysis.id}>{analysis.caseRef || 'Unassigned case'} · {analysis.clipName} · {analysis.transactionTime}</option>)}</select></section>
      {packet ? <section className="response-panel handoff-preview" aria-label="Handoff packet preview"><div className="handoff-document-head"><div className="handoff-mark">DR</div><div><span>DRISHTI · LOCAL REVIEW WORKSPACE</span><h3>Demonstration handoff summary</h3><small>Prepared {stamp()} · By {user.displayName}</small></div><span className="handoff-draft">DRAFT</span></div>
        <div className="handoff-warning"><AlertTriangle size={16} /><span>SIMULATION ONLY. This is not an official report, dispatch, or certified chain-of-custody record.</span></div>
        <div className="handoff-meta"><div><span>Case reference</span><strong>{packet.case.reference}</strong></div><div><span>Transaction reference</span><strong>{packet.case.transactionReference || 'Not recorded'}</strong></div><div><span>Transaction time</span><strong>{packet.case.transactionTime}</strong></div><div><span>Review state</span><strong>{packet.review.analysisStatus}</strong></div></div>
        <div className="handoff-section"><h4>Evidence reference</h4>{packet.evidence.length ? packet.evidence.map((item) => <div className="handoff-evidence" key={item.clipId}><strong>{item.filename}</strong><span>{item.camera} · added {new Date(item.uploadedAt).toLocaleString('en-IN')}</span><code>SHA-256 {item.sha256}</code><small>{item.note}</small></div>) : <p>No matching local video clip is available for this analysis.</p>}</div>
        <div className="handoff-section"><h4>Human review summary</h4><p>{packet.review.summary} Candidate frames require human verification; similarity and quality values are not identity findings.</p><div className="handoff-counts"><span>{packet.review.candidateCounts.total} surfaced</span><span>{packet.review.candidateCounts.selected} selected</span><span>{packet.review.candidateCounts.rejected} rejected</span><span>{packet.review.candidateCounts.awaitingReview} awaiting review</span></div>{selectedAnalysis && <button className="text-button" onClick={() => onReview(selectedAnalysis.id)}>Open evidence review <ArrowDownToLine size={13} /></button>}</div>
        <div className="handoff-section"><h4>Local audit context</h4><p>{packet.audit.entriesChecked} local entries checked · {packet.audit.localChainVerified ? 'hash links verified at last check' : 'integrity not verified'}.</p><small>{packet.audit.limitation}</small></div>
        <div className="handoff-footer">No video, face images, or external notifications are included. Use approved secure transfer and review procedures for real cases.</div>
      </section> : <div className="response-empty">Load or analyze the synthetic demo case to prepare a sample handoff.</div>}
    </>}

    {view === 'custody' && <>
      <div className="response-overview"><div><span className="response-eyebrow">WORKSPACE HISTORY · LOCAL VIEW</span><h2>Activity & custody context</h2><p>Separates the real local audit feed from this screen’s simulated response actions.</p></div><span className={`custody-integrity ${auditIntegrity?.verified ? 'verified' : ''}`}><span />{auditIntegrity?.verified ? 'Local chain links verified' : 'Local chain not verified'}</span></div>
      <div className="custody-grid"><section className="response-panel custody-panel"><div className="response-panel-head"><div><span className="response-eyebrow">ACTUAL WORKSPACE RECORDS</span><h3>Local audit activity</h3></div><span className="custody-count">{audit.length} entries</span></div><p className="custody-limit">These entries come from the local prototype audit feed. They are not independently protected or a complete legal custody record.</p>{audit.length ? <ol className="custody-list">{audit.slice(0, 30).map((item) => <li key={item.id}><i /><div><strong>{item.action.replaceAll('_', ' ')}</strong><span>{item.note || item.description || item.subjectId}</span><time>{new Date(item.occurredAt).toLocaleString('en-IN')}</time></div></li>)}</ol> : <div className="response-empty">No local audit entries are available yet.</div>}</section>
        <section className="response-panel custody-panel"><div className="response-panel-head"><div><span className="response-eyebrow">BROWSER-LOCAL SIMULATION</span><h3>Response desk actions</h3></div><span className="custody-count">{demo.log.length} entries</span></div><p className="custody-limit">Fictional scenario actions stored in this browser only. These entries do not modify the application audit log.</p><ol className="custody-list">{demo.log.map((item) => <li key={item.id}><i /><div><strong>{item.action}</strong><span>{item.detail}</span><time>{new Date(item.at).toLocaleString('en-IN')} · {item.by}</time></div></li>)}</ol></section></div>
      <div className="response-bottom-note"><AlertTriangle size={16} /><span>Hash-linked local logs and browser demo history do not establish independent custody. Operational deployment needs protected audit storage, identity controls, and verified handoff procedures.</span></div>
    </>}
  </div>;
}
