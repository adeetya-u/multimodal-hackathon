/**
 * Landing intro voice via Vapi — general knee demo, no patient chart.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../lib/apiBase";
import {
  registerVapiListener,
  resetVapiSpeechDedupe,
  speakViaVapi,
  startVapiCall,
  stopVapiCall,
  getActiveVapiCaseId,
  formatVapiError,
} from "./vapiSession";
import { parseVapiTranscriptMessage, normalizeTranscriptText } from "../utils/vapiTranscript";
import {
  upsertTranscriptTurn,
  coerceTranscriptText,
  type TranscriptTurn,
} from "../utils/transcriptTurns";

const introAssistantId = import.meta.env.VITE_VAPI_INTRO_ASSISTANT_ID as string | undefined;
const UTTERANCE_DEBOUNCE_MS = 500;
const AGENT_PENDING_ID = "agent-pending";
const WELCOME_TURN_ID = "agent-welcome";
const DEFAULT_INTRO_WELCOME = "Hi, I'm Scalpel. Ask anything about knee surgery!";

function introWelcomeMessage(overrides?: Record<string, unknown>): string {
  const raw = overrides?.firstMessage;
  return typeof raw === "string" && raw.trim() ? raw.trim() : DEFAULT_INTRO_WELCOME;
}

function withWelcomeTurn(turns: IntroTurn[], welcome: string): IntroTurn[] {
  return upsertTranscriptTurn(turns, {
    id: WELCOME_TURN_ID,
    role: "agent",
    text: welcome,
    ts: Date.now() / 1000,
  });
}

export type IntroConnection = "idle" | "connecting" | "connected" | "error";

export type IntroTurn = TranscriptTurn;

const READY_PREFETCH = {
  status: "ready" as const,
  warmup: { agents: 1, skipped: null as string | null },
  credentials: null,
  error: null as string | null,
};

function withoutAgentPending(turns: IntroTurn[]): IntroTurn[] {
  return turns.filter((t) => t.id !== AGENT_PENDING_ID);
}

function speakIntroAnswer(spoken: string): void {
  if (speakViaVapi(spoken, { interruptAssistant: true, force: true })) {
    return;
  }
  window.setTimeout(() => {
    speakViaVapi(spoken, { interruptAssistant: true, force: true });
  }, 400);
}

function withAgentPending(turns: IntroTurn[]): IntroTurn[] {
  const base = withoutAgentPending(turns);
  return upsertTranscriptTurn(base, {
    id: AGENT_PENDING_ID,
    role: "agent",
    text: "…",
    ts: Date.now() / 1000,
    interim: true,
  });
}

export function useVapiIntroRoom() {
  const [connection, setConnection] = useState<IntroConnection>("idle");
  const [error, setError] = useState<string | null>(null);
  const [agentConnected, setAgentConnected] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<IntroTurn[]>([]);
  const [wantsPrep, setWantsPrep] = useState(false);
  const [agentActivity, setAgentActivity] = useState<"idle" | "searching" | "speaking">("idle");
  const lastPostedUtteranceRef = useRef("");
  const utteranceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingUtteranceRef = useRef("");
  const introOverridesRef = useRef<Record<string, unknown> | undefined>(undefined);

  useEffect(() => {
    void apiFetch("/api/intro/warmup", { method: "POST" })
      .then(async (res) => {
        if (!res.ok) return;
        const data = (await res.json()) as { assistantOverrides?: Record<string, unknown> };
        introOverridesRef.current = data.assistantOverrides;
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    return () => {
      if (utteranceTimerRef.current) clearTimeout(utteranceTimerRef.current);
      if (getActiveVapiCaseId() === "intro") {
        void stopVapiCall();
      }
    };
  }, []);

  useEffect(() => {
    return registerVapiListener({
      onCallStart: () => {
        setConnection("connected");
        setAgentConnected(true);
        setMicActive(true);
      },
      onCallEnd: () => {
        setConnection("idle");
        setAgentConnected(false);
        setMicActive(false);
        setAgentActivity("idle");
      },
      onSpeechStart: () => setAgentActivity("speaking"),
      onSpeechEnd: () => setAgentActivity((prev) => (prev === "speaking" ? "idle" : prev)),
      onMessage: (message) => {
        const parsed = parseVapiTranscriptMessage(message);
        if (!parsed) return;

        const { role, text, interim } = parsed;
        if (role === "agent") return;

        const turn: IntroTurn = {
          id: interim ? `interim-${role}` : `${role}-${Date.now()}`,
          role,
          text,
          ts: Date.now() / 1000,
          interim,
        };

        setTranscript((prev) => {
          const next = upsertTranscriptTurn(prev, turn);
          if (!interim && role === "surgeon") {
            const lastSurgeon = [...next].reverse().find((t) => t.role === "surgeon" && !t.interim);
            if (lastSurgeon) {
              pendingUtteranceRef.current = lastSurgeon.text;
              if (utteranceTimerRef.current) clearTimeout(utteranceTimerRef.current);
              utteranceTimerRef.current = setTimeout(() => {
                const pending = pendingUtteranceRef.current.trim();
                if (!pending) return;
                const norm = normalizeTranscriptText(pending);
                if (lastPostedUtteranceRef.current === norm) return;
                lastPostedUtteranceRef.current = norm;
                setAgentActivity("searching");
                setTranscript((t) => withAgentPending(t));
                void apiFetch("/api/intro/utterance", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ text: pending }),
                })
                  .then(async (res) => {
                    if (!res.ok) {
                      lastPostedUtteranceRef.current = "";
                      const detail = await res.text().catch(() => "");
                      setError(detail || "Could not process question");
                      setTranscript((t) => withoutAgentPending(t));
                      return;
                    }
                    const data = (await res.json()) as { spoken?: string };
                    const spoken = coerceTranscriptText(data.spoken);
                    if (spoken) {
                      const agentTurn: IntroTurn = {
                        id: `agent-${Date.now()}`,
                        role: "agent",
                        text: spoken,
                        ts: Date.now() / 1000,
                      };
                      setTranscript((t) =>
                        upsertTranscriptTurn(withoutAgentPending(t), agentTurn),
                      );
                      if (/prep|upload|case/i.test(spoken)) {
                        setWantsPrep(true);
                      }
                      speakIntroAnswer(spoken);
                      setAgentActivity("speaking");
                    } else {
                      setTranscript((t) => withoutAgentPending(t));
                    }
                  })
                  .catch(() => {
                    lastPostedUtteranceRef.current = "";
                    setError("Network error processing speech");
                    setTranscript((t) => withoutAgentPending(t));
                  })
                  .finally(() =>
                    setAgentActivity((prev) => (prev === "searching" ? "idle" : prev)),
                  );
              }, UTTERANCE_DEBOUNCE_MS);
            }
          }
          return next;
        });
      },
      onError: (err) => {
        setConnection("error");
        setError(formatVapiError(err));
      },
    });
  }, []);

  const connect = useCallback(async () => {
    if (!introAssistantId) {
      setConnection("error");
      setError("VITE_VAPI_INTRO_ASSISTANT_ID is not set");
      return;
    }
    setConnection("connecting");
    setError(null);
    setTranscript([]);
    setWantsPrep(false);
    setMicError(null);
    lastPostedUtteranceRef.current = "";
    resetVapiSpeechDedupe();
    try {
      let overrides = introOverridesRef.current;
      if (!overrides) {
        const res = await apiFetch("/api/intro/warmup", { method: "POST" });
        if (res.ok) {
          const data = (await res.json()) as { assistantOverrides?: Record<string, unknown> };
          overrides = data.assistantOverrides;
          introOverridesRef.current = overrides;
        }
      }
      const welcome = introWelcomeMessage(overrides);
      await startVapiCall("intro", introAssistantId, {
        muted: false,
        assistantOverrides: overrides,
      });
      setTranscript(withWelcomeTurn([], welcome));
      setConnection("connected");
      setAgentConnected(true);
      setMicActive(true);
    } catch (err) {
      setConnection("error");
      setError(formatVapiError(err, "Could not connect"));
    }
  }, []);

  const disconnect = useCallback(async () => {
    if (utteranceTimerRef.current) clearTimeout(utteranceTimerRef.current);
    await stopVapiCall();
    setConnection("idle");
    setAgentConnected(false);
    setMicActive(false);
    setWantsPrep(false);
    setAgentActivity("idle");
  }, []);

  return {
    connection,
    prefetch: READY_PREFETCH,
    demoReady: Boolean(introAssistantId),
    error,
    agentConnected,
    micActive,
    micError,
    transcript,
    wantsPrep,
    agentActivity,
    connect,
    disconnect,
  };
};
