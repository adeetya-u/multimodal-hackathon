/**
 * OR voice session via Vapi + SSE event bridge from webhook orchestrator.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch, apiUrl } from "../lib/apiBase";
import type { AgentActivity, AgentMode, ChecklistState, ConnectionState, SituationCard } from "../types";
import { resolveCaseId } from "../utils/caseStorage";
import { mergeChecklistProgress } from "../utils/checklistMerge";
import {
  registerVapiListener,
  resetVapiSpeechDedupe,
  resetVapiClient,
  speakViaVapi,
  startVapiCall,
  stopVapiCall,
  formatVapiError,
} from "./vapiSession";
import { parseVapiTranscriptMessage, normalizeTranscriptText } from "../utils/vapiTranscript";
import { upsertTranscriptTurn, coerceTranscriptText, type TranscriptTurn as BaseTranscriptTurn } from "../utils/transcriptTurns";
import { isVoicePipelineReady } from "./voiceSessionHealth";

const assistantId = import.meta.env.VITE_VAPI_OR_ASSISTANT_ID as string | undefined;
const UTTERANCE_DEBOUNCE_MS = 850;

/** Match backend `time.time()` seconds (SSE/webhook); tolerate ms payloads. */
function normalizeTranscriptTs(raw: number): number {
  return raw >= 1e11 ? raw / 1000 : raw;
}

export interface TranscriptTurn extends BaseTranscriptTurn {}

export function useVapiORSession(options: { autoConnect?: boolean } = {}) {
  const { autoConnect = true } = options;
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [caseId, setCaseId] = useState<string | null>(null);
  const [caseReady, setCaseReady] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<ChecklistState | null>(null);
  const [listening, setListening] = useState(false);
  const [agentConnected, setAgentConnected] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const micError: string | null = null;
  const [agentMode, setAgentMode] = useState<AgentMode>("logger");
  const situationCards: SituationCard[] = [];
  const [groundedDisplay, setGroundedDisplay] = useState<SituationCard | null>(null);
  const [agentActivity, setAgentActivity] = useState<AgentActivity>("idle");
  const [agentResponsive, setAgentResponsive] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [bootstrapAck, setBootstrapAck] = useState(false);
  const [endingCase, setEndingCase] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const caseIdRef = useRef<string | null>(null);
  const connectAttemptRef = useRef(0);
  const lastPostedUtteranceRef = useRef("");
  const utteranceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingUtteranceRef = useRef("");
  const endCaseRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    caseIdRef.current = caseId;
  }, [caseId]);

  useEffect(() => {
    let cancelled = false;
    void resolveCaseId(searchParams.get("case"))
      .then((id) => {
        if (!cancelled) {
          setCaseId(id);
          setCaseReady(true);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCaseId(null);
          setCaseReady(true);
          setError(err instanceof Error ? err.message : "Could not resolve case");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  useEffect(() => {
    if (!caseReady) return;
    const url = caseId ? `/api/checklist?case_id=${caseId}` : "/api/checklist";
    const controller = new AbortController();
    apiFetch(url, { signal: controller.signal })
      .then((r) => r.json())
      .then((data: ChecklistState) => setChecklist((prev) => mergeChecklistProgress(prev, data)))
      .catch(() => {});
    return () => controller.abort();
  }, [caseId, caseReady]);

  const handleVoiceEvent = useCallback((topic: string, payload: Record<string, unknown>) => {
    if (topic === "surgical-checklist") {
      setChecklist((prev) => mergeChecklistProgress(prev, payload as unknown as ChecklistState));
    }
    if (topic === "agent-mode" && payload.mode) {
      const mode = String(payload.mode);
      setAgentMode(
        mode === "query"
          ? "query"
          : mode === "situation"
            ? "situation"
            : mode === "summary"
              ? "summary"
              : "logger",
      );
    }
    if (topic === "grounded-display") {
      const card = payload as unknown as SituationCard;
      const spoken = coerceTranscriptText(card?.spoken_text);
      setGroundedDisplay(spoken ? { ...card, spoken_text: spoken } : null);
    }
    if (topic === "agent-status" && payload.status) {
      const s = String(payload.status);
      if (s === "searching" || s === "thinking") setAgentActivity("searching");
      else if (s === "closing" || s === "speaking") setAgentActivity("speaking");
      else setAgentActivity("idle");
    }
    if (topic === "case-bootstrap-ack" && payload.ok) {
      setBootstrapAck(true);
    }
    if (topic === "case-closed") {
      void endCaseRef.current?.();
    }
    if (topic === "transcript" && payload.role) {
      const text = coerceTranscriptText(payload.text ?? payload.transcript ?? payload.message);
      if (!text) return;
      const role = payload.role === "agent" ? "agent" : "surgeon";
      const turn: TranscriptTurn = {
        id: String(payload.id ?? `${role}-${Date.now()}`),
        role,
        text,
        ts: normalizeTranscriptTs(Number(payload.ts ?? Date.now() / 1000)),
      };
      setTranscript((prev) => upsertTranscriptTurn(prev, turn));
      if (role === "agent") {
        setAgentResponsive(true);
        lastPostedUtteranceRef.current = "";
        if (speakViaVapi(turn.text)) {
          setAgentActivity("speaking");
        }
      }
    }
  }, [navigate]);

  const connectSSE = useCallback((cid: string) => {
    eventSourceRef.current?.close();
    const es = new EventSource(apiUrl(`/api/cases/${cid}/voice/stream`));
    eventSourceRef.current = es;
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { topic?: string; payload?: Record<string, unknown> };
        if (data.topic) handleVoiceEvent(data.topic, data.payload ?? {});
      } catch { /* ignore */ }
    };
  }, [handleVoiceEvent]);

  const connect = useCallback(async () => {
    if (!caseId || !assistantId) {
      setError("Vapi is not configured (VITE_VAPI_PUBLIC_KEY / VITE_VAPI_OR_ASSISTANT_ID)");
      setConnection("error");
      return;
    }
    const attempt = ++connectAttemptRef.current;
    setConnection("connecting");
    setError(null);
    lastPostedUtteranceRef.current = "";
    resetVapiSpeechDedupe();
    try {
      await resetVapiClient();
      if (attempt !== connectAttemptRef.current) return;
      const res = await apiFetch(`/api/cases/${caseId}/voice/start`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      if (attempt !== connectAttemptRef.current) return;
      const payload = (await res.json()) as {
        assistantId?: string;
        assistantOverrides?: Record<string, unknown>;
      };
      connectSSE(caseId);
      await startVapiCall(caseId, payload.assistantId || assistantId, {
        muted: false,
        assistantOverrides: payload.assistantOverrides,
      });
      if (attempt !== connectAttemptRef.current) return;
      setMicActive(true);
      setListening(true);
      setAgentConnected(true);
      setAgentResponsive(true);
      setBootstrapAck(true);
      setConnection("connected");
    } catch (err) {
      if (attempt !== connectAttemptRef.current) return;
      const message = formatVapiError(err, "Connection failed");
      if (message === "Voice start cancelled") return;
      setConnection("error");
      setError(message);
    }
  }, [caseId, assistantId, connectSSE]);

  const disconnect = useCallback(async () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    await stopVapiCall();
    if (caseId) await apiFetch(`/api/cases/${caseId}/voice-leave`, { method: "POST" }).catch(() => {});
    setConnection("idle");
    setListening(false);
    setAgentConnected(false);
    setMicActive(false);
  }, [caseId]);

  const endCase = useCallback(async () => {
    if (!caseId) return;
    setEndingCase(true);
    try {
      await apiFetch(`/api/cases/${caseId}/session/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checklist, transcript }),
      });
      const res = await apiFetch(`/api/cases/${caseId}/close`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      navigate(`/summary?case=${caseId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not close case");
    } finally {
      await disconnect();
      setEndingCase(false);
    }
  }, [caseId, checklist, transcript, disconnect, navigate]);

  useEffect(() => {
    endCaseRef.current = endCase;
  }, [endCase]);

  useEffect(() => {
    return registerVapiListener({
      onCallStart: () => {
        setAgentConnected(true);
        setConnection("connected");
        setMicActive(true);
        setListening(true);
      },
      onCallEnd: () => {
        setConnection("idle");
        setListening(false);
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

        const turn: TranscriptTurn = {
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
                const cid = caseIdRef.current;
                const pending = pendingUtteranceRef.current.trim();
                if (!cid || !pending) return;
                const norm = normalizeTranscriptText(pending);
                if (lastPostedUtteranceRef.current === norm) return;
                lastPostedUtteranceRef.current = norm;
                setAgentActivity("searching");
                void apiFetch(`/api/cases/${cid}/voice/utterance`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ text: pending }),
                })
                  .then(async (res) => {
                    if (!res.ok) {
                      lastPostedUtteranceRef.current = "";
                      const detail = await res.text().catch(() => "");
                      setError(detail || "Could not process utterance");
                      return;
                    }
                    const data = (await res.json()) as {
                      spoken?: string;
                      checklist?: ChecklistState;
                      duplicate?: boolean;
                      close_case?: boolean;
                    };
                    if (data.checklist) {
                      setChecklist((prevCl) => mergeChecklistProgress(prevCl, data.checklist!));
                    }
                    if (data.close_case) {
                      void endCaseRef.current?.();
                      return;
                    }
                    const spoken = coerceTranscriptText(data.spoken);
                    if (spoken && !data.duplicate && speakViaVapi(spoken)) {
                      setAgentActivity("speaking");
                    }
                  })
                  .catch(() => {
                    lastPostedUtteranceRef.current = "";
                    setError("Network error processing speech");
                  })
                  .finally(() => setAgentActivity("idle"));
              }, UTTERANCE_DEBOUNCE_MS);
            }
          }
          return next;
        });
      },
      onError: (err) => {
        setConnection("error");
        setError(formatVapiError(err));
        setMicActive(false);
      },
    });
  }, []);

  useEffect(() => {
    if (!autoConnect || !caseReady || !caseId) return;
    void connect();
    return () => {
      connectAttemptRef.current += 1;
    };
  }, [autoConnect, caseReady, caseId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    return () => {
      void disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const voiceReady = isVoicePipelineReady(agentResponsive, bootstrapAck, micActive);

  return {
    caseId,
    connection,
    error,
    checklist,
    listening,
    agentConnected,
    micActive,
    micError,
    agentMode,
    situationCards,
    groundedDisplay,
    agentActivity,
    agentResponsive,
    transcript,
    bootstrapAck,
    voiceReady,
    endingCase,
    currentStep: checklist?.steps.find((s) => s.status === "in_progress")?.label ?? "",
    connect,
    disconnect,
    endCase,
    redispatchAgent: connect,
  };
}
