/**
 * Singleton Vapi Web SDK session per tab.
 * Serialized start/stop so concurrent connects (Strict Mode, warmup → OR) cannot
 * tear down a call while start() is still running.
 */
import Vapi from "@vapi-ai/web";
import { vapiTranscriberOverride, vapiVoicePipelineOverrides } from "../utils/vapiVoicePipeline";

const publicKey = import.meta.env.VITE_VAPI_PUBLIC_KEY as string | undefined;

let vapi: Vapi | null = null;
let activeCaseId: string | null = null;
let activeSessionId: string | null = null;
let startGeneration = 0;
let startChain: Promise<void> = Promise.resolve();

export type VapiListener = {
  onCallStart?: () => void;
  onCallEnd?: () => void;
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
  onMessage?: (message: unknown) => void;
  onError?: (error: unknown) => void;
};

const listeners = new Set<VapiListener>();

function notify(fn: (l: VapiListener) => void) {
  for (const l of listeners) fn(l);
}

function runExclusive<T>(fn: () => Promise<T>): Promise<T> {
  const next = startChain.then(fn, fn);
  startChain = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

function ensureVapi(): Vapi {
  if (!publicKey) throw new Error("VITE_VAPI_PUBLIC_KEY is not set");
  if (!vapi) {
    vapi = new Vapi(publicKey, undefined, { alwaysIncludeMicInPermissionPrompt: true }, { startAudioOff: false });
    vapi.on("call-start", () => notify((l) => l.onCallStart?.()));
    vapi.on("call-end", () => {
      activeCaseId = null;
      activeSessionId = null;
      notify((l) => l.onCallEnd?.());
    });
    vapi.on("speech-start", () => notify((l) => l.onSpeechStart?.()));
    vapi.on("speech-end", () => notify((l) => l.onSpeechEnd?.()));
    vapi.on("message", (message) => notify((l) => l.onMessage?.(message)));
    vapi.on("error", (error) => {
      if (shouldSuppressError()) return;
      notify((l) => l.onError?.(error));
    });
  }
  return vapi;
}

let suppressErrorsUntil = 0;

function markIntentionalTeardown(ms = 800): void {
  suppressErrorsUntil = Date.now() + ms;
}

function shouldSuppressError(): boolean {
  return Date.now() < suppressErrorsUntil;
}

function coerceErrorText(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || null;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value instanceof Error) return value.message.trim() || null;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const key of ["message", "msg", "errorMsg", "errorDetail", "reason", "detail", "description"]) {
      const text = coerceErrorText(obj[key]);
      if (text) return text;
    }
    if ("error" in obj) {
      const text = coerceErrorText(obj.error);
      if (text) return text;
    }
    try {
      const json = JSON.stringify(value);
      return json === "{}" ? null : json;
    } catch {
      return null;
    }
  }
  return String(value);
}

function extractVapiError(error: unknown): string {
  return coerceErrorText(error) ?? "Voice connection failed";
}

export function formatVapiError(error: unknown, fallback = "Voice connection failed"): string {
  return coerceErrorText(error) ?? fallback;
}

function waitForCallStart(client: Vapi, timeoutMs = 45_000): Promise<void> {
  if (client.getDailyCallObject()) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const finish = (done: () => void) => {
      clearTimeout(timer);
      client.removeListener("call-start", onStart);
      client.removeListener("error", onError);
      done();
    };

    const onStart = () => finish(resolve);
    const onError = (error: unknown) => {
      finish(() => reject(new Error(extractVapiError(error))));
    };
    const timer = setTimeout(
      () => finish(() => reject(new Error("Voice call timed out waiting for agent"))),
      timeoutMs,
    );

    client.on("call-start", onStart);
    client.on("error", onError);
  });
}

async function stopVapiCallInternal(): Promise<void> {
  if (!vapi) return;
  markIntentionalTeardown();
  try {
    await vapi.stop();
  } catch {
    /* call may already be destroyed */
  }
  activeCaseId = null;
  activeSessionId = null;
}

async function destroyStaleCall(client: Vapi): Promise<void> {
  markIntentionalTeardown();
  // Always call stop — the SDK keeps an internal `started` flag even without a Daily object.
  try {
    await client.stop();
  } catch {
    /* call may already be destroyed */
  }
  activeCaseId = null;
  activeSessionId = null;
  for (let i = 0; i < 20; i += 1) {
    if (!client.getDailyCallObject()) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

function safeSetMuted(client: Vapi, muted: boolean): void {
  if (!client.getDailyCallObject()) return;
  try {
    client.setMuted(muted);
  } catch {
    /* call torn down between check and mute */
  }
}

function throwIfCancelled(generation: number): void {
  if (generation !== startGeneration) {
    throw new Error("Voice start cancelled");
  }
}

export function registerVapiListener(listener: VapiListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function resetVapiClient(): Promise<void> {
  startGeneration += 1;
  await runExclusive(async () => {
    await resetVapiClientInternal();
  });
}

async function resetVapiClientInternal(): Promise<void> {
  markIntentionalTeardown();
  if (vapi) {
    try {
      await vapi.stop();
    } catch {
      /* ignore */
    }
  }
  vapi = null;
  activeCaseId = null;
  activeSessionId = null;
}

export async function stopVapiCall(): Promise<void> {
  startGeneration += 1;
  await runExclusive(async () => {
    await stopVapiCallInternal();
    activeCaseId = null;
    activeSessionId = null;
  });
}

export async function startVapiCall(
  caseId: string,
  assistantId: string,
  opts: { muted?: boolean; assistantOverrides?: Record<string, unknown> } = {},
): Promise<string> {
  return runExclusive(async () => {
    const generation = startGeneration;
    let client = ensureVapi();
    const sessionId = crypto.randomUUID();

    const transcriberModel =
      (import.meta.env.VITE_VAPI_TRANSCRIBER_MODEL as string | undefined) || "nova-3-medical";
    const baseOverrides = {
      metadata: { case_id: caseId, client_session_id: sessionId },
      variableValues: { case_id: caseId, client_session_id: sessionId },
      ...vapiVoicePipelineOverrides(),
      transcriber: vapiTranscriberOverride(transcriberModel),
    };
    const mergedOverrides = {
      ...baseOverrides,
      ...opts.assistantOverrides,
      metadata: {
        ...baseOverrides.metadata,
        ...(opts.assistantOverrides?.metadata as Record<string, unknown> | undefined),
        case_id: caseId,
        client_session_id: sessionId,
      },
      variableValues: {
        ...baseOverrides.variableValues,
        ...(opts.assistantOverrides?.variableValues as Record<string, unknown> | undefined),
        case_id: caseId,
        client_session_id: sessionId,
      },
    };

    const startOnce = async (activeClient: Vapi) => {
      await destroyStaleCall(activeClient);
      throwIfCancelled(generation);
      activeCaseId = caseId;
      activeSessionId = sessionId;

      let lastStartError: string | null = null;
      const onStartError = (error: unknown) => {
        lastStartError = extractVapiError(error);
      };
      activeClient.on("error", onStartError);

      try {
        const callStartWait = waitForCallStart(activeClient);
        const result = await activeClient.start(
          assistantId,
          mergedOverrides,
          undefined,
          undefined,
          undefined,
          { roomDeleteOnUserLeaveEnabled: true },
        );
        throwIfCancelled(generation);
        if (result === null) {
          throw new Error(lastStartError || "Voice start returned no call");
        }
        await callStartWait;
        throwIfCancelled(generation);
        return result;
      } finally {
        activeClient.removeListener("error", onStartError);
      }
    };

    try {
      let result: Awaited<ReturnType<Vapi["start"]>>;
      try {
        result = await startOnce(client);
      } catch {
        await resetVapiClientInternal();
        throwIfCancelled(generation);
        client = ensureVapi();
        await new Promise((resolve) => setTimeout(resolve, 250));
        result = await startOnce(client);
      }

      if (!result) {
        throw new Error("Could not start voice call — refresh the page and try again");
      }

      safeSetMuted(client, Boolean(opts.muted));
      return sessionId;
    } catch (err) {
      await destroyStaleCall(client);
      activeCaseId = null;
      activeSessionId = null;
      throw err;
    }
  });
}

export function setVapiMuted(muted: boolean): void {
  if (!vapi) return;
  safeSetMuted(vapi, muted);
}

export function getVapiClient(): Vapi | null {
  return vapi;
}

export function getActiveVapiCaseId(): string | null {
  return activeCaseId;
}

export function getActiveVapiSessionId(): string | null {
  return activeSessionId;
}

let lastSpokenNorm = "";

/** Speak a grounded answer through the active Vapi call (deduped). */
export function speakViaVapi(
  message: string,
  opts: { interruptAssistant?: boolean; force?: boolean } = {},
): boolean {
  const text = message.trim();
  if (!text) return false;
  if (/^(noted\.?|checking\.?|one moment\.?|got it\.?)$/i.test(text)) return false;
  const norm = text.toLowerCase().replace(/\s+/g, " ");
  if (!opts.force && lastSpokenNorm === norm) return false;
  const client = getVapiClient();
  if (!client?.getDailyCallObject()) return false;
  try {
    const interrupt = opts.interruptAssistant ?? true;
    client.say(text, false, false, interrupt);
    lastSpokenNorm = norm;
    return true;
  } catch {
    return false;
  }
}

export function resetVapiSpeechDedupe(): void {
  lastSpokenNorm = "";
}
