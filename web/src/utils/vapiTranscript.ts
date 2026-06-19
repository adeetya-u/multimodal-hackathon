/** Normalize Vapi Web SDK transcript events — avoid conversation-update dupes. */

import type { TranscriptRole } from "./transcriptTurns";
import { coerceTranscriptText } from "./transcriptTurns";

export type ParsedVapiTranscript = {
  role: TranscriptRole;
  text: string;
  interim: boolean;
};

function unwrapMessage(message: unknown): Record<string, unknown> {
  if (!message || typeof message !== "object") return {};
  const root = message as Record<string, unknown>;
  if (root.message && typeof root.message === "object") {
    return root.message as Record<string, unknown>;
  }
  return root;
}

function roleFrom(raw: unknown): TranscriptRole {
  return String(raw || "").toLowerCase() === "assistant" ? "agent" : "surgeon";
}

function interimFrom(msg: Record<string, unknown>): boolean {
  const t = String(msg.transcriptType || msg.transcript_type || "").toLowerCase();
  return t === "partial";
}

export function parseVapiTranscriptMessage(message: unknown): ParsedVapiTranscript | null {
  const msg = unwrapMessage(message);
  const type = String(msg.type || "").toLowerCase();

  if (type !== "transcript" && !type.startsWith("transcript")) {
    return null;
  }

  const text = coerceTranscriptText(msg.transcript ?? msg.text ?? msg.message ?? msg.content);
  if (!text) return null;
  return { role: roleFrom(msg.role), text, interim: interimFrom(msg) };
}

export { normalizeTranscriptText, coerceTranscriptText } from "./transcriptTurns";
