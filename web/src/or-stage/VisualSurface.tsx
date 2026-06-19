import type { RichCard } from "./types";
import { GuidelinePage } from "./GuidelinePage";

interface Props {
  card: RichCard;
}

export function VisualSurface({ card }: Props) {
  if (card.kind === "guideline" || card.kind === "text" || card.kind === "external") {
    return (
      <div className="or-stage-visual-surface or-stage-visual-surface--doc">
        <GuidelinePage card={card} />
      </div>
    );
  }

  return (
    <div className="or-stage-visual-surface or-stage-visual-surface--doc or-stage-text-card">
      <p className="or-stage-text-card-body">{card.excerpt}</p>
    </div>
  );
}
