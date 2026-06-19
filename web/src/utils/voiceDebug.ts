/** Voice pipeline debug — toggles for STT, TTS, and general pipeline logs. */

export interface VoiceDebugEvent {
  ts: number;
  kind: string;
  detail?: string;
  data?: unknown;
}

const MAX_EVENTS = 120;
const events: VoiceDebugEvent[] = [];
const listeners = new Set<() => void>();

export type PipelineComponent = "stt" | "tts" | "pipeline";

const TOGGLE_KEYS: Record<PipelineComponent, string> = {
  stt: "voice_log_stt",
  tts: "voice_log_tts",
  pipeline: "voice_log_pipeline",
};

export function isVoiceDebugEnabled(): boolean {
  if (import.meta.env.DEV) return true;
  try {
    return new URLSearchParams(window.location.search).get("voice_debug") === "1";
  } catch {
    return false;
  }
}

export function isPipelineLogEnabled(component: PipelineComponent): boolean {
  if (!isVoiceDebugEnabled()) return false;
  try {
    const stored = sessionStorage.getItem(TOGGLE_KEYS[component]);
    if (stored === "0") return false;
    if (stored === "1") return true;
  } catch {
    /* ignore */
  }
  // Default: STT+pipeline on, TTS off (noisy)
  return component !== "tts";
}

export function setPipelineLogEnabled(component: PipelineComponent, enabled: boolean): void {
  try {
    sessionStorage.setItem(TOGGLE_KEYS[component], enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
  for (const fn of listeners) fn();
}

export function voiceDebugLog(kind: string, detail?: string, data?: unknown): void {
  if (!isVoiceDebugEnabled()) return;

  const component: PipelineComponent | null =
    kind === "stt" || kind.startsWith("stt") ? "stt"
    : kind === "tts" || kind.startsWith("tts") ? "tts"
    : kind === "pipeline" || kind.startsWith("pipeline") ? "pipeline"
    : null;

  if (component && !isPipelineLogEnabled(component)) return;

  const entry: VoiceDebugEvent = { ts: Date.now(), kind, detail, data };
  events.push(entry);
  if (events.length > MAX_EVENTS) events.shift();
  for (const fn of listeners) fn();

  const prefix = `[voice:${kind}]`;
  if (data !== undefined) console.info(prefix, detail ?? "", data);
  else if (detail) console.info(prefix, detail);
  else console.info(prefix);
}

export function pipelineEventFromAgent(payload: Record<string, unknown>): void {
  const component = String(payload.component ?? "pipeline") as PipelineComponent;
  const event = String(payload.event ?? "event");
  if (!isPipelineLogEnabled(component)) return;
  voiceDebugLog(component, event, payload);
}

export function getVoiceDebugEvents(): VoiceDebugEvent[] {
  return [...events];
}

export function subscribeVoiceDebug(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function formatDebugTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 1,
  });
}
