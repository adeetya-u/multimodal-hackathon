import { useMemo } from "react";
import { coerceTranscriptText } from "../utils/transcriptTurns";
import { useLoggerRoom } from "../hooks/useLoggerRoom";
import { pickPrimaryCard } from "./types";
import type { AnswerMeta } from "./VoiceStage.types";
import { useEmulatedVitals } from "./useEmulatedVitals";

export function useORStage() {
  const room = useLoggerRoom({ autoConnect: true });
  const vitals = useEmulatedVitals();
  const primaryCard = useMemo(() => {
    if (room.groundedDisplay) return room.groundedDisplay as import("./types").RichCard;
    return pickPrimaryCard(room.situationCards);
  }, [room.groundedDisplay, room.situationCards]);

  const answerMeta = useMemo((): AnswerMeta | null => {
    const card = room.groundedDisplay;
    if (!card?.spoken_text) return null;
    return {
      spokenText: coerceTranscriptText(card.spoken_text),
      citation: typeof card.citation === "string" ? card.citation : typeof card.title === "string" ? card.title : typeof card.source === "string" ? card.source : undefined,
      confidence: card.confidence ?? card.score,
    };
  }, [room.groundedDisplay]);

  return { ...room, primaryCard, answerMeta, vitals };
}
