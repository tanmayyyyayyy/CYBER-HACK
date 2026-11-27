const artwork = new URL('./assets/drishti-logo.svg', import.meta.url).href;

type LogoProps = {
  variant?: 'mark' | 'lockup';
  decorative?: boolean;
};

export function Logo({ variant = 'mark', decorative = false }: LogoProps) {
  const lockup = variant === 'lockup';
  return (
    <svg
      className={`drishti-logo drishti-logo--${variant}`}
      viewBox={lockup ? '0 0 1302 887' : '0 0 686 617'}
      role={decorative ? undefined : 'img'}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : 'Drishti Digital Forensics'}
      focusable="false"
    >
      <use href={`${artwork}#${variant}`} width="100%" height="100%" />
    </svg>
  );
}
