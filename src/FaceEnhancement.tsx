import { useState } from 'react';
import { api, type Analysis, type Candidate, type FaceEnhancement } from './api';

export default function CrossCameraFaceReview({ analyses, initialCandidateId }: { analyses: Analysis[]; initialCandidateId?: string }) {
  const [ids, setIds] = useState<string[]>(initialCandidateId ? [initialCandidateId] : []);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<FaceEnhancement | null>(null);
  const sources = analyses.filter((item) =>
    item.status === 'completed' && item.candidates.some((crop) => crop.trackId > 0),
  );
  const selected = sources.flatMap((item) => item.candidates.filter((crop) => ids.includes(crop.id)));
  const ready = new Set(selected.map((crop) => crop.clipId)).size >= 2;

  function toggle(crop: Candidate) {
    setIds(ids.includes(crop.id) ? ids.filter((id) => id !== crop.id) : [...ids, crop.id]);
    setConfirmed(false);
    setResult(null);
    setError('');
  }

  async function combine() {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(await api.enhanceFaces(selected.map((crop) => crop.id)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Face enhancement failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel intake-panel cross-camera-review">
      <h2>Cross-camera face enhancement</h2>
      <p>Analyze a time window in each uploaded clip. Compare the detected tracks and select up to 12 face crops from at least two clips.</p>
      {sources.map((item) => (
        <details key={item.id}>
          <summary>{item.clipName} � {item.transactionTime} � {item.caseRef || 'Unassigned case'}</summary>
          <div className="cross-camera-crops">
            {item.candidates.filter((crop) => crop.trackId > 0).map((crop) => {
              const checked = ids.includes(crop.id);
              const otherTrack = selected.some((other) => other.clipId === crop.clipId &&
                (other.trackId !== crop.trackId || other.analysisId !== crop.analysisId));
              return (
                <label key={crop.id}>
                  <img src={crop.imageUrl} alt={`Track ${crop.trackId} at ${crop.timeLabel}`} loading="lazy" />
                  <span><input type="checkbox" checked={checked} onChange={() => toggle(crop)}
                    disabled={busy || (!checked && (otherTrack || selected.length >= 12))} /> Track {crop.trackId} � {crop.timeLabel}</span>
                </label>
              );
            })}
          </div>
        </details>
      ))}
      {!sources.length && <p>Complete footage analysis to see tracks with visible face crops.</p>}
      {selected.length > 0 && (
        <div className="cross-camera-crops">
          {selected.map((crop) => (
            <figure key={crop.id}>
              <img src={crop.imageUrl} alt={`Selected track ${crop.trackId}`} />
              <figcaption>
                <a href={`/api/clips/${crop.clipId}/video#t=${crop.time}`} target="_blank" rel="noreferrer">
                  {sources.find((item) => item.id === crop.analysisId)?.clipName} � {crop.timeLabel}
                </a>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      <label>
        <input type="checkbox" checked={confirmed && ready} disabled={!ready || busy}
          onChange={(event) => setConfirmed(event.target.checked)} /> I confirm these frames show the same person.
      </label>
      <div>
        <button className="button button-compact" type="button" disabled={!ready || !confirmed || busy}
          onClick={() => void combine()}>{busy ? 'Aligning frames.' : 'Enhance confirmed frames'}</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {result && (
        <figure className="cross-camera-result">
          <img src={result.imageUrl} alt={result.fused ? 'Multi-camera enhanced crop' : 'Best original face crop'} />
          <figcaption>
            {result.fused ? 'Enhanced review image' : 'Best original crop � insufficient cross-camera alignment'}
            <ul>{result.sources.map((source) => (
              <li key={source.id}>{sources.find((item) => item.id === source.analysisId)?.clipName} � {source.timeLabel} � Track {source.trackId}</li>
            ))}</ul>
          </figcaption>
        </figure>
      )}
    </section>
  );
}
