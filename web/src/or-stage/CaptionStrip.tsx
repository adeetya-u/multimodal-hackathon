import type { RichCard } from "./types";

interface Props {
  card: RichCard;
  spokenText?: string;
}

function formatCaption(card: RichCard): string {
  if (card.citation) return card.citation;
  if (card.title && card.pages) return `${card.title} p.${card.pages}`;
  if (card.title) return card.title;
  const parts = card.source.split("/");
  return parts[parts.length - 1].replace(/_/g, " ");
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <span className="or-stage-confidence">
      <span
        className="or-stage-confidence-bar"
        style={{ width: `${pct}%` }}
        aria-hidden
      />
      <span className="or-stage-confidence-label">{pct}%</span>
    </span>
  );
}

export function CaptionStrip({ card, spokenText }: Props) {
  return (
    <div className="or-stage-caption-strip">
      {spokenText && (
        <p className="or-stage-caption-spoken">{spokenText}</p>
      )}
      <span className="or-stage-caption-source">{formatCaption(card)}</span>
      {card.score != null && card.score > 0 && <ConfidenceBar score={card.score} />}
      <span className="or-stage-verify-notice">Verify before acting</span>
    </div>
  );
}
