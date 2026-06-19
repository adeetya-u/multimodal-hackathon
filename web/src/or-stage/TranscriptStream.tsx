import { useEffect, useRef } from "react";
import type { TranscriptTurn } from "./types";

interface Props {
  turns: TranscriptTurn[];
  compact?: boolean;
  listening?: boolean;
}

export function TranscriptStream({ turns, compact = false, listening = false }: Props) {
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = streamRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  if (turns.length === 0) {
    return (
      <div
        ref={streamRef}
        className={compact ? "or-stage-transcript-strip or-stage-transcript-empty" : "or-stage-transcript-stream or-stage-transcript-empty"}
      >
        <span className="or-stage-transcript-hint">
          {listening
            ? "Your words will appear here…"
            : compact
              ? "Waiting…"
              : "Waiting for voice input…"}
        </span>
      </div>
    );
  }

  return (
    <div
      ref={streamRef}
      className={compact ? "or-stage-transcript-strip" : "or-stage-transcript-stream"}
      role="log"
      aria-live="polite"
    >
      {turns.map((turn) => (
        <div
          key={turn.id}
          className={`or-stage-turn or-stage-turn-${turn.role}${turn.interim ? " or-stage-turn-interim" : ""}`}
        >
          <span className="or-stage-turn-role">
            {turn.role === "surgeon" ? "You" : "Assistant"}
            {turn.interim ? " · live" : ""}
          </span>
          <p className="or-stage-turn-text">{turn.text}</p>
        </div>
      ))}
    </div>
  );
}
