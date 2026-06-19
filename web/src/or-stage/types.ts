import type { SituationCard } from "../types";
import type { TranscriptTurn } from "../hooks/useLoggerRoom";

export type { TranscriptTurn };

export type CardKind = "guideline" | "text" | "external";

export interface GuidelineRef {
  pdf_url: string;
  page: number;
  highlight_snippet?: string;
}

export interface RichCard extends SituationCard {
  kind: CardKind;
  guideline?: GuidelineRef;
}

export function toPrimaryCardKey(card: RichCard): string {
  return `${card.kind}:${card.source}`;
}

export function pickPrimaryCard(cards: SituationCard[]): RichCard | null {
  if (!cards.length) return null;
  const rich = cards.map(toRichCard);
  return (
    rich.find((c) => c.kind === "guideline") ??
    rich[0]
  );
}

function toRichCard(card: SituationCard): RichCard {
  const base = card as RichCard;
  return { ...base, kind: base.kind ?? "text" };
}
