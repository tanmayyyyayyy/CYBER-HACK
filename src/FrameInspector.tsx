import { useEffect, useRef, useState } from 'react';
import type { Candidate, Clip } from './api';

type Props = { candidate: Candidate; clip?: Clip; onClose: () => void };

export default function FrameInspector({ candidate, clip, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [brightness, setBrightness] = useState(100);
  const [contrast, setContrast] = useState(100);
  const [saturation, setSaturation] = useState(100);
  const [sharpness, setSharpness] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [showMarker, setShowMarker] = useState(true);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const controls = dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), input:not(:disabled)');
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose]);

  useEffect(() => {
    let active = true;
    const source = new Image();
    setImage(null);
    setLoadError(false);
    source.onload = () => { if (active) setImage(source); };
    source.onerror = () => { if (active) setLoadError(true); };
    source.src = candidate.frameUrl || `/api/candidates/${candidate.id}/frame`;
    return () => { active = false; source.onload = null; source.onerror = null; };
  }, [candidate.id, candidate.frameUrl]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image) return;
    const context = canvas.getContext('2d', { willReadFrequently: sharpness > 0 });
    if (!context) return;
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    context.drawImage(image, 0, 0);
    if (sharpness === 0) return;

    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    const original = pixels.data;
    const result = new Uint8ClampedArray(original);
    const stride = canvas.width * 4;
    const amount = sharpness / 100 * 0.65;
    for (let y = 1; y < canvas.height - 1; y++) {
      for (let x = 1; x < canvas.width - 1; x++) {
        const index = y * stride + x * 4;
        for (let channel = 0; channel < 3; channel++) {
          const center = original[index + channel];
          const neighbors = original[index - stride + channel] + original[index + stride + channel]
            + original[index - 4 + channel] + original[index + 4 + channel];
          result[index + channel] = center + amount * (4 * center - neighbors);
        }
      }
    }
    pixels.data.set(result);
    context.putImageData(pixels, 0, 0);
  }, [image, sharpness]);

  const bbox = candidate.bbox;
  const marker = image && bbox?.length === 4 && bbox[2] > bbox[0] && bbox[3] > bbox[1] ? {
    left: `${bbox[0] / image.naturalWidth * 100}%`,
    top: `${bbox[1] / image.naturalHeight * 100}%`,
    width: `${(bbox[2] - bbox[0]) / image.naturalWidth * 100}%`,
    height: `${(bbox[3] - bbox[1]) / image.naturalHeight * 100}%`,
  } : null;
  const reset = () => { setBrightness(100); setContrast(100); setSaturation(100); setSharpness(0); setZoom(100); };

  return <div className="inspector-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} className="inspector-dialog" role="dialog" aria-modal="true" aria-label="Poora video frame dekhein">
      <header className="inspector-header">
        <div><span className="overline">Video ka original scene</span><h2>Poora frame dekhein</h2><p>{clip?.filename || 'Video'} · {candidate.timeLabel} · Person {candidate.trackId}</p></div>
        <button ref={closeRef} type="button" className="inspector-close" onClick={onClose} aria-label="Full frame band karein">Band karein ×</button>
      </header>
      <div className="inspector-layout">
        <div className="inspector-main">
          <div className="inspector-toolbar">
            <label htmlFor="frame-zoom">Zoom</label>
            <select id="frame-zoom" value={zoom} onChange={(event) => setZoom(Number(event.target.value))}>
              <option value={100}>Poora scene</option><option value={150}>1.5×</option><option value={200}>2×</option>
            </select>
            {marker && <button type="button" className="inspector-marker-toggle" aria-pressed={showMarker} onClick={() => setShowMarker((visible) => !visible)}>{showMarker ? 'Peela mark hatayein' : 'Chehra mark karein'}</button>}
          </div>
          <div className="inspector-stage">
            {!image && !loadError && <p role="status">Poora scene khul raha hai…</p>}
            {loadError && <p role="alert">Frame nahi khul saka. Video dobara check karein.</p>}
            <div className="inspector-image-wrap" style={{ width: `${zoom}%`, display: image ? 'block' : 'none' }}>
              <canvas ref={canvasRef} role="img" aria-label={`Poora video frame, ${candidate.timeLabel}`} style={{ filter: `brightness(${brightness}%) contrast(${contrast}%) saturate(${saturation}%)` }} />
              {showMarker && marker && <span className="inspector-face-marker" style={marker} aria-hidden="true" />}
            </div>
          </div>
          <p className="inspector-footnote">Peela box system ka lagbhag face mark hai. Zoom karke scene ko scroll se dekh sakte hain.</p>
        </div>
        <aside className="inspector-controls">
          <div className="inspector-reference"><span>Chuna hua face crop</span><img src={candidate.imageUrl} alt={`Person ${candidate.trackId} ka face crop`} /></div>
          <h3>Dekhne ke liye badlein</h3>
          <InspectorSlider id="brightness" label="Roshni" value={brightness} min={50} max={180} onChange={setBrightness} />
          <InspectorSlider id="contrast" label="Contrast" value={contrast} min={50} max={180} onChange={setContrast} />
          <InspectorSlider id="saturation" label="Rang" value={saturation} min={0} max={180} onChange={setSaturation} />
          <InspectorSlider id="sharpness" label="Sharpness" value={sharpness} min={0} max={100} onChange={setSharpness} />
          <button type="button" className="secondary inspector-reset" onClick={reset}>Sab reset karein</button>
          <p>Ye badlav sirf screen par hain. Original video aur evidence file waise hi rehte hain.</p>
        </aside>
      </div>
    </section>
  </div>;
}

function InspectorSlider({ id, label, value, min, max, onChange }: { id: string; label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  return <div className="inspector-slider"><div><label htmlFor={`inspect-${id}`}>{label}</label><output htmlFor={`inspect-${id}`}>{value}%</output></div><input id={`inspect-${id}`} type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} /></div>;
}
