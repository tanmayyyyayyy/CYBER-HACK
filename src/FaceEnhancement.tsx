import { useState } from 'react';
import './face-comparison.css';
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
  const ready = selected.length >= 4 && selected.length <= 5;

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
      <h2>Best face from 4–5 frames</h2>
      <p>Choose four or five frames of the same person from one clip or several clips. Pick one person track per clip.</p>
      {sources.map((item) => (
        <details key={item.id}>
          <summary title={item.clipName}>
            <span className="cross-camera-source-name">{item.clipName}</span>
            <small>{item.transactionTime} · {item.candidates.length} face crops</small>
          </summary>
          <div className="cross-camera-crops">
            {item.candidates.filter((crop) => crop.trackId > 0).map((crop) => {
              const checked = ids.includes(crop.id);
              const otherTrack = selected.some((other) => other.clipId === crop.clipId &&
                (other.trackId !== crop.trackId || other.analysisId !== crop.analysisId));
              return (
                <label key={crop.id} className="cross-camera-crop" data-selected={checked}>
                  <img src={crop.imageUrl} alt={`Track ${crop.trackId} at ${crop.timeLabel}`} loading="lazy" />
                  <span><input type="checkbox" checked={checked} onChange={() => toggle(crop)}
                    disabled={busy || (!checked && (otherTrack || selected.length >= 5))} /> Track {crop.trackId} · {crop.timeLabel}</span>
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
            <figure key={crop.id} className="cross-camera-selected">
              <img src={crop.imageUrl} alt={`Selected track ${crop.trackId}`} />
              <figcaption>
                <a href={`/api/clips/${crop.clipId}/video#t=${crop.time}`} target="_blank" rel="noreferrer" title={sources.find((item) => item.id === crop.analysisId)?.clipName}>
                  Video dekhein · {crop.timeLabel}
                </a>
                {result?.frameScores.find((item) => item.id === crop.id)?.score != null &&
                  <small> · {result.frameScores.find((item) => item.id === crop.id)?.score}/100</small>}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      <label className="cross-camera-confirm">
        <input type="checkbox" checked={confirmed && ready} disabled={!ready || busy}
          onChange={(event) => setConfirmed(event.target.checked)} /> I confirm these frames show the same person.
      </label>
      <div>
        <button className="button button-compact cross-camera-action" type="button" disabled={!ready || !confirmed || busy}
          onClick={() => void combine()}>{busy ? 'Aligning and scoring frames…' : 'Generate best face image'}</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {result && <FaceResult result={result} sources={sources} />}
    </section>
  );
}


function FaceResult({ result, sources }: { result: FaceEnhancement; sources: Analysis[] }) {
  const frames = result.sourceFrames ?? result.sources;
  return (
    <figure className="cross-camera-result">
      {result.fused && result.bestOriginal ? (
        <div className="face-result-comparison">
          <figure><img src={result.bestOriginal.imageUrl} alt="Highest-scoring original face crop" />
            <figcaption>Best original · {result.bestOriginalScore}/100 · {result.bestOriginal.timeLabel}</figcaption>
          </figure>
          <figure><img src={result.imageUrl} alt="Multi-frame face picture for review" />
            <figcaption>Combined · {result.quality.score}/100</figcaption>
          </figure>
        </div>
      ) : <img src={result.imageUrl} alt={result.fused ? 'Multi-frame enhanced crop' : 'Best original face crop'} />}
      <figcaption>
        <strong>{result.fused ? `Combined from ${frames.length} frames` : 'Best original crop'} · {result.quality.score}/100</strong>
        {result.fallbackReason && <p>{result.fallbackReason}</p>}
        {result.nearbyFusion && <p>Aligned nearby source frames around a selected crop. Review image.</p>}
        <p>Best original {result.bestOriginalScore}/100. Quality estimates how usable the image is for face comparison.</p>
        {result.quality.metrics && <p>
          Sharpness {result.quality.metrics.sharpness} · Lighting {result.quality.metrics.illumination} ·
          Pose {result.quality.metrics.pose} · Size {result.quality.metrics.faceSize} ·
          Detector confidence {result.quality.metrics.confidence}
        </p>}
        <details>
          <summary>How the score works</summary>
          <p>Sharpness 32%, lighting 22%, pose 20%, face size 14%, and detector confidence 12%. Possible occlusion reduces the score.</p>
        </details>
        {result.quality.flags.length > 0 && <p>{result.quality.flags.join(' · ')}</p>}
        <a href={result.imageUrl} download="drishti-final-face.png">Download final image</a>
        <ul>{frames.map((source) => (
          <li key={`${source.clipId}:${source.time}`}>{sources.find((item) => item.id === source.analysisId)?.clipName ?? 'Source video'} · <a href={`/api/clips/${source.clipId}/video#t=${source.time}`} target="_blank" rel="noreferrer">{source.timeLabel}</a> · Track {source.trackId}</li>
        ))}</ul>
      </figcaption>
    </figure>
  );
}

export function TrackFacePicture({ analysis, frames, onResult }: { analysis: Analysis; frames: Candidate[]; onResult?: (result: FaceEnhancement) => void }) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<FaceEnhancement | null>(null);
  const track = String(frames[0].trackId).padStart(2, '0');
  const scope = frames.every((frame) => frame.reviewStatus === 'selected') ? 'marked' : 'available';

  async function generate() {
    setBusy(true);
    setResult(null);
    setError('');
    try {
      const picture = await api.enhanceFaces(frames.map((frame) => frame.id), true);
      setResult(picture);
      onResult?.(picture);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not generate the review picture.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="track-face-picture" aria-label="Best picture for this track">
      <h3>Best picture for Track {track}</h3>
      <p>{frames.length} {scope} {frames.length === 1 ? 'frame' : 'frames'} for review</p>
      <label className="cross-camera-confirm">
        <input type="checkbox" checked={confirmed} disabled={busy}
          onChange={(event) => setConfirmed(event.target.checked)} /> I confirm these frames show the same person.
      </label>
      <button type="button" className="button button-outline button-compact cross-camera-action" disabled={!confirmed || busy}
        onClick={() => void generate()}>{busy ? 'Checking frame quality…' : 'Generate best picture'}</button>
      {busy && <span className="sr-only" role="status">Checking frame quality</span>}
      {error && <p role="alert">{error}</p>}
      {result && <FaceResult result={result} sources={[analysis]} />}
    </section>
  );
}
