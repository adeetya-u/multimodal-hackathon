import { useEffect, useMemo, useRef } from "react";
import { coerceTranscriptText, lastCompleteLine } from "../utils/transcriptTurns";
import type { TranscriptTurn } from "./types";
import { ScalpelLogo } from "../components/ScalpelLogo";
import { VoiceVisualizer } from "./VoiceVisualizer";
import type { AnswerMeta } from "./VoiceStage.types";

export type { AnswerMeta } from "./VoiceStage.types";

interface Props {
  turns: TranscriptTurn[];
  voiceActive: boolean;
  agentReady: boolean;
  micActive: boolean;
  micError: string | null;
  connectionError?: string | null;
  searching?: boolean;
  speaking?: boolean;
  answerMeta?: AnswerMeta | null;
  agentResponsive?: boolean;
  voiceReady?: boolean;
}

function idleStatus(
  voiceActive: boolean,
  agentReady: boolean,
  micActive: boolean,
  micError: string | null,
  connectionError: string | null,
  agentResponsive: boolean,
  voiceReady: boolean,
): string | null {
  if (connectionError) return connectionError;
  if (!voiceActive) return "Connecting voice…";
  if (!agentReady) return "Waiting for agent…";
  if (!micActive) return micError ?? "Allow microphone to speak";
  if (!agentResponsive) return "Voice agent starting…";
  if (!voiceReady) return "Setting up session…";
  return "Listening. Speak naturally.";
}

function formatConfidence(confidence?: number): string | null {
  if (confidence == null || Number.isNaN(confidence)) return null;
  const pct = confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence);
  return `${pct}% match`;
}

export function VoiceStage({
  turns,
  voiceActive,
  agentReady,
  micActive,
  micError,
  connectionError = null,
  searching = false,
  speaking = false,
  answerMeta = null,
  agentResponsive = false,
  voiceReady = false,
}: Props) {
  const { lastSurgeon, lastAgent } = useMemo(() => {
    let surgeon: TranscriptTurn | undefined;
    let agent: TranscriptTurn | undefined;
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const turn = turns[i];
      if (turn.interim) continue;
      if (!surgeon && turn.role === "surgeon") surgeon = turn;
      if (!agent && turn.role === "agent") agent = turn;
      if (surgeon && agent) break;
    }
    const liveSurgeon = [...turns].reverse().find((t) => t.role === "surgeon" && t.interim);
    return { lastSurgeon: liveSurgeon ?? surgeon, lastAgent: agent };
  }, [turns]);

  const agentText = lastCompleteLine(answerMeta?.spokenText || lastAgent?.text || "");
  const showAgent = Boolean(agentText);
  const showSearching = searching && !showAgent && !speaking;
  const showIdle = !lastSurgeon && !showAgent && !showSearching;
  const isLongAnswer = agentText.length > 120;
  const confidenceLabel = formatConfidence(answerMeta?.confidence);
  const heroRef = useRef<HTMLDivElement>(null);
  const listening = voiceActive && micActive && voiceReady;

  useEffect(() => {
    const el = heroRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lastSurgeon?.text, agentText, showSearching]);

  const idleMessage = showIdle
    ? idleStatus(voiceActive, agentReady, micActive, micError, connectionError, agentResponsive, voiceReady)
    : null;

  return (
    <section className="or-voice-stage" aria-label="Voice conversation">
      <div className="or-voice-viz-zone">
        <VoiceVisualizer active={listening} />
        {listening && (
          <span className="or-voice-listening-pill" aria-live="polite">
            {speaking ? "Assistant speaking" : searching ? "Searching chart" : "Listening"}
          </span>
        )}
      </div>

      <div
        ref={heroRef}
        className={`or-voice-hero${!showIdle ? " or-voice-hero--active" : ""}`}
        role="log"
        aria-live="polite"
      >
        {idleMessage && (
          <div className="or-voice-hero-idle">
            <ScalpelLogo size="lg" className="or-voice-idle-logo" />
            <p className="or-voice-hero-empty">{idleMessage}</p>
          </div>
        )}
        {lastSurgeon && (
          <div
            className={`or-voice-hero-block or-voice-hero-block--you${
              lastSurgeon.interim ? " or-voice-hero-block--interim" : ""
            }`}
          >
            <span className="or-voice-hero-label">
              You{lastSurgeon.interim ? " · live" : ""}
            </span>
            <p className="or-voice-hero-text">{coerceTranscriptText(lastSurgeon.text)}</p>
          </div>
        )}
        {showSearching && (
          <div className="or-voice-hero-block or-voice-hero-block--agent or-voice-hero-block--searching">
            <span className="or-voice-hero-label">Assistant</span>
            <p className="or-voice-hero-searching">Searching…</p>
          </div>
        )}
        {showAgent && (
          <div
            className={`or-voice-hero-block or-voice-hero-block--agent${
              speaking ? " or-voice-hero-block--speaking" : ""
            }`}
          >
            <span className="or-voice-hero-label">
              Assistant{speaking ? " · speaking" : ""}
            </span>
            <p
              className={`or-voice-hero-text or-voice-hero-text--agent${
                isLongAnswer ? " or-voice-hero-text--long" : ""
              }`}
            >
              {agentText}
            </p>
            {answerMeta?.citation && (
              <p className="or-voice-hero-citation">
                {answerMeta.citation}
                {confidenceLabel ? ` · ${confidenceLabel}` : ""}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
