/** Shared transcript turn merge/dedupe for Vapi partial + final events. */

export type TranscriptRole = "surgeon" | "agent";

export interface TranscriptTurn {
  id: string;
  role: TranscriptRole;
  text: string;
  ts: number;
  interim?: boolean;
}

/** Vapi/Deepgram may send transcript as a string or nested object — never render raw objects. */
export function coerceTranscriptText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value).trim();
  if (Array.isArray(value)) {
    return value.map(coerceTranscriptText).filter(Boolean).join(" ").trim();
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const key of ["text", "transcript", "message", "content", "utterance"]) {
      if (key in obj) {
        const inner = coerceTranscriptText(obj[key]);
        if (inner) return inner;
      }
    }
    if (Array.isArray(obj.words)) {
      const fromWords = obj.words
        .map((w) => {
          if (typeof w === "string") return w;
          if (w && typeof w === "object" && "word" in (w as object)) {
            return String((w as { word?: string }).word ?? "");
          }
          return "";
        })
        .filter(Boolean)
        .join(" ")
        .trim();
      if (fromWords) return fromWords;
    }
    if (Array.isArray(obj.alternatives)) {
      return coerceTranscriptText(obj.alternatives);
    }
  }
  return "";
}

export function normalizeTranscriptText(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

/** Last finished sentence or line — avoids showing stacked/repeated agent transcripts. */
export function lastCompleteLine(text: string): string {
  const trimmed = coerceTranscriptText(text);
  if (!trimmed) return "";

  const lines = trimmed.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  if (lines.length > 1) return lines[lines.length - 1] ?? trimmed;

  const sentences = trimmed
    .match(/[^.!?]+(?:[.!?]+|$)/g)
    ?.map((sentence) => sentence.trim())
    .filter(Boolean);
  if (sentences?.length) return sentences[sentences.length - 1] ?? trimmed;

  return trimmed;
}

const SENTENCE_END = /[.?!]\s*$/;
const MERGE_WINDOW_MS = 8000;

function findLastFinalTurn(turns: TranscriptTurn[], role: TranscriptRole): TranscriptTurn | undefined {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const t = turns[i];
    if (!t.interim && t.role === role) return t;
  }
  return undefined;
}

function shouldContinuePrevious(prev: TranscriptTurn, next: TranscriptTurn): boolean {
  if (prev.role !== next.role) return false;
  if (next.ts - prev.ts > MERGE_WINDOW_MS) return false;
  const prevNorm = normalizeTranscriptText(prev.text);
  const nextNorm = normalizeTranscriptText(next.text);
  if (prevNorm === nextNorm) return false;
  if (nextNorm.startsWith(prevNorm) || prevNorm.startsWith(nextNorm)) return true;
  if (!SENTENCE_END.test(prev.text.trim())) return true;
  if (/^(or|and|but|a|an|the|to|for|in|with|of|at|on|one|i)\b/i.test(next.text.trim())) return true;
  return false;
}

function mergeTurnText(prev: TranscriptTurn, next: TranscriptTurn): string {
  const prevNorm = normalizeTranscriptText(prev.text);
  const nextNorm = normalizeTranscriptText(next.text);
  if (nextNorm.startsWith(prevNorm)) return next.text.trim();
  if (prevNorm.startsWith(nextNorm)) return prev.text.trim();
  return `${prev.text.trim()} ${next.text.trim()}`.replace(/\s+/g, " ").trim();
}

export function upsertTranscriptTurn(prev: TranscriptTurn[], turn: TranscriptTurn): TranscriptTurn[] {
  const normalizedTurn: TranscriptTurn = {
    ...turn,
    text: coerceTranscriptText(turn.text),
  };
  if (!normalizedTurn.text) return prev;

  const withoutInterim = prev.filter((t) => !(t.interim && t.role === normalizedTurn.role));

  if (normalizedTurn.interim) {
    return [...withoutInterim, normalizedTurn].slice(-200);
  }

  const norm = normalizeTranscriptText(normalizedTurn.text);
  let next = withoutInterim.filter((t) => !t.interim || t.role !== normalizedTurn.role);

  const dupeIdx = next.findIndex(
    (t) => !t.interim && t.role === normalizedTurn.role && normalizeTranscriptText(t.text) === norm,
  );
  if (dupeIdx >= 0) {
    next[dupeIdx] = { ...next[dupeIdx], ...normalizedTurn, id: next[dupeIdx].id };
    return next.slice(-200);
  }

  const lastFinal = findLastFinalTurn(next, normalizedTurn.role);
  if (lastFinal && shouldContinuePrevious(lastFinal, normalizedTurn)) {
    const merged: TranscriptTurn = {
      ...lastFinal,
      text: mergeTurnText(lastFinal, normalizedTurn),
      ts: normalizedTurn.ts,
      interim: false,
    };
    return [...next.filter((t) => t.id !== lastFinal.id), merged].slice(-200);
  }

  return [...next.filter((t) => t.id !== normalizedTurn.id), normalizedTurn].slice(-200);
}
