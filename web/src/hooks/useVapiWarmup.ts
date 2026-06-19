/**
 * Prep voice warmup via Vapi — muted call + SSE until ready for OR.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiUrl } from "../lib/apiBase";
import type { IngestionStage } from "./useCasePrep";
import {
  registerVapiListener,
  startVapiCall,
  stopVapiCall,
  formatVapiError,
} from "./vapiSession";
import { markVoiceBootstrapAck } from "../utils/voiceDispatch";

const assistantId = import.meta.env.VITE_VAPI_OR_ASSISTANT_ID as string | undefined;
const DISPATCH_STAGES = new Set<IngestionStage>(["indexing", "ready"]);
const CONNECT_STAGES = new Set<IngestionStage>(["ready"]);

export type VoiceWarmupState =
  | "idle"
  | "dispatching"
  | "connecting"
  | "warming"
  | "ready"
  | "error";

const WARMUP_PROGRESS: Record<VoiceWarmupState, number> = {
  idle: 0,
  dispatching: 0.25,
  connecting: 0.5,
  warming: 0.75,
  ready: 1,
  error: 0,
};

export function warmupProgressForState(state: VoiceWarmupState, ingestionReady: boolean): number {
  if (!ingestionReady) return 0;
  return WARMUP_PROGRESS[state];
}

export function warmupStatusLabel(
  state: VoiceWarmupState,
  ingestionReady: boolean,
): string | null {
  if (!ingestionReady) return null;
  switch (state) {
    case "dispatching":
      return "Warming voice agent…";
    case "connecting":
      return "Connecting…";
    case "warming":
      return "Waiting for agent…";
    case "ready":
      return "Ready for OR";
    case "error":
      return "Voice warmup failed";
    default:
      return "Preparing voice…";
  }
}

export function useVapiWarmup(caseId: string | null, stage: IngestionStage) {
  const [warmupState, setWarmupState] = useState<VoiceWarmupState>("idle");
  const [error, setError] = useState<string | null>(null);
  const bootstrapAckRef = useRef(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const warmupAttemptRef = useRef(0);

  const markReady = useCallback(() => {
    if (caseId) markVoiceBootstrapAck(caseId);
    bootstrapAckRef.current = true;
    setWarmupState("ready");
    setError(null);
  }, [caseId]);

  useEffect(() => {
    if (!caseId || !DISPATCH_STAGES.has(stage)) return;
    setWarmupState((prev) => (prev === "ready" ? "ready" : "dispatching"));
    void apiFetch(`/api/cases/${caseId}/warm-voice`, { method: "POST" }).catch(() => {});
  }, [caseId, stage]);

  useEffect(() => {
    if (!caseId || !CONNECT_STAGES.has(stage) || !assistantId) return;

    const attempt = ++warmupAttemptRef.current;
    setWarmupState("connecting");
    setError(null);

    const es = new EventSource(apiUrl(`/api/cases/${caseId}/voice/stream`));
    eventSourceRef.current = es;
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { topic?: string; payload?: Record<string, unknown> & { ok?: boolean } };
        if (data.topic === "case-bootstrap-ack" && data.payload?.ok) markReady();
      } catch { /* ignore */ }
    };

    void (async () => {
      try {
        const res = await apiFetch(`/api/cases/${caseId}/voice/start`, { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        if (attempt !== warmupAttemptRef.current) return;
        const payload = (await res.json()) as {
          assistantId?: string;
          assistantOverrides?: Record<string, unknown>;
        };
        setWarmupState("warming");
        await startVapiCall(caseId, payload.assistantId || assistantId, {
          muted: true,
          assistantOverrides: payload.assistantOverrides,
        });
        if (attempt !== warmupAttemptRef.current) return;
        markReady();
      } catch (err) {
        if (attempt !== warmupAttemptRef.current) return;
        const message = formatVapiError(err, "Voice warmup failed");
        if (message === "Voice start cancelled") return;
        setWarmupState("error");
        setError(message);
      }
    })();

    return () => {
      warmupAttemptRef.current += 1;
      es.close();
      eventSourceRef.current = null;
      void stopVapiCall();
    };
  }, [caseId, stage, markReady]);

  useEffect(() => {
    return registerVapiListener({
      onCallStart: () => markReady(),
    });
  }, [markReady]);

  return {
    warmupState,
    warmupReady: warmupState === "ready",
    warmupProgress: warmupProgressForState(warmupState, stage === "ready"),
    error,
  };
}
