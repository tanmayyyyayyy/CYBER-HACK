import { useEffect, useState } from 'react';

const phrases = [
  { lang: 'en', prefix: 'The ', accent: 'investigation', suffix: ' begins here.', hold: 2500 },
  { lang: 'hi', prefix: '', accent: 'जांच', suffix: ' यहीं से शुरू होती है।', hold: 2500 },
  { lang: 'hi-Latn', prefix: '', accent: 'Investigation', suffix: ' yahan se shuru hoti hai.', hold: 4000 },
];
const hinglish = phrases[2];
const motionQuery = '(prefers-reduced-motion: reduce)';
const initialFrame = { index: 0, length: 0 };
const sequence = typeof Intl.Segmenter === 'function' ? phrases.map((phrase) => {
  const segmenter = new Intl.Segmenter(phrase.lang, { granularity: 'grapheme' });
  const graphemes = Array.from(segmenter.segment(phrase.prefix + phrase.accent + phrase.suffix), ({ segment }) => segment);
  return { ...phrase, graphemes };
}) : null;

function randomDelay(min: number, max: number) {
  return min + Math.random() * (max - min);
}

export default function LoginHeadline() {
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia(motionQuery).matches);
  const [frame, setFrame] = useState(initialFrame);

  useEffect(() => {
    const preference = window.matchMedia(motionQuery);
    function updatePreference() {
      setFrame(initialFrame);
      setReducedMotion(preference.matches);
    }
    preference.addEventListener('change', updatePreference);
    return () => preference.removeEventListener('change', updatePreference);
  }, []);

  useEffect(() => {
    if (reducedMotion || !sequence) return;
    const lines = sequence;
    let index = 0;
    let length = 0;
    let timer = window.setTimeout(type, 500);

    function type() {
      const phrase = lines[index];
      length += 1;
      setFrame({ index, length });
      if (length === phrase.graphemes.length) {
        timer = window.setTimeout(erase, phrase.hold);
      } else {
        timer = window.setTimeout(type, randomDelay(65, 95));
      }
    }

    function erase() {
      length -= 1;
      setFrame({ index, length });
      if (length > 0) {
        timer = window.setTimeout(erase, randomDelay(30, 45));
      } else {
        index = (index + 1) % lines.length;
        timer = window.setTimeout(type, 400);
      }
    }

    return () => window.clearTimeout(timer);
  }, [reducedMotion]);

  const phrase = reducedMotion ? undefined : sequence?.[frame.index];
  const visible = phrase ?? hinglish;
  const shown = phrase ? phrase.graphemes.slice(0, frame.length).join('') : hinglish.accent + hinglish.suffix;
  const accentStart = visible.prefix.length;
  const accentEnd = accentStart + visible.accent.length;

  return <h1 className="auth-headline" aria-label={hinglish.accent + hinglish.suffix} lang={hinglish.lang}>
    {phrases.map(({ lang, prefix, accent, suffix }) => (
      <span key={lang} className="auth-headline-measure" lang={lang} aria-hidden="true">{prefix}{accent}{suffix}</span>
    ))}
    <span className={phrase ? 'auth-headline-text auth-headline-enter' : 'auth-headline-text'} lang={visible.lang} aria-hidden="true">
      {shown.slice(0, accentStart)}<span className="auth-headline-accent">{shown.slice(accentStart, accentEnd)}</span>{shown.slice(accentEnd)}{phrase && <span className="auth-headline-cursor" />}
    </span>
  </h1>;
}
