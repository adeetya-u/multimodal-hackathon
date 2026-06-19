type ScalpelLogoSize = "xs" | "sm" | "md" | "lg" | "xl";

interface ScalpelLogoProps {
  size?: ScalpelLogoSize;
  /** Show "Scalpel" text beside the mark */
  showWordmark?: boolean;
  className?: string;
  alt?: string;
}

const HEIGHT: Record<ScalpelLogoSize, number> = {
  xs: 24,
  sm: 32,
  md: 40,
  lg: 56,
  xl: 72,
};

/** Scalpel wizard mark (transparent PNG). */
export function ScalpelLogo({
  size = "md",
  showWordmark = false,
  className = "",
  alt = "Scalpel",
}: ScalpelLogoProps) {
  const height = HEIGHT[size];

  return (
    <span className={`scalpel-logo ${className}`.trim()}>
      <img
        src="/scalpel-logo.png"
        alt={alt}
        height={height}
        width={Math.round(height * 0.92)}
        className={`scalpel-logo-img scalpel-logo-img--${size}`}
        decoding="async"
      />
      {showWordmark ? <span className="scalpel-logo-wordmark">Scalpel</span> : null}
    </span>
  );
}
