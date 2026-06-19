/** Vapi turn-taking defaults — keep in sync with backend/cases/voice/provider.py */

function envInt(name: keyof ImportMetaEnv, fallback: number): number {
  const raw = import.meta.env[name];
  if (raw === undefined || raw === "") return fallback;
  const parsed = Number.parseInt(String(raw), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function envFloat(name: keyof ImportMetaEnv, fallback: number): number {
  const raw = import.meta.env[name];
  if (raw === undefined || raw === "") return fallback;
  const parsed = Number.parseFloat(String(raw));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

export function vapiTranscriberOverride(model: string) {
  return {
    provider: "deepgram" as const,
    model,
    language: "en",
    endpointing: envInt("VITE_VAPI_TRANSCRIBER_ENDPOINTING_MS", 500),
    smartFormat: true,
    keywords: [
      "Scalpel",
      "allergies",
      "allergy",
      "penicillin",
      "arthroplasty",
      "checklist",
      "DVT",
      "antibiotic",
    ],
    fallbackPlan: { autoFallback: { enabled: true } },
  };
}

export function vapiVoicePipelineOverrides() {
  return {
    startSpeakingPlan: {
      waitSeconds: envFloat("VITE_VAPI_START_WAIT_SEC", 0.75),
      transcriptionEndpointingPlan: {
        onPunctuationSeconds: envFloat("VITE_VAPI_ENDPOINT_PUNCT_SEC", 0.65),
        onNoPunctuationSeconds: clamp(
          envFloat("VITE_VAPI_ENDPOINT_NO_PUNCT_SEC", 2.8),
          0.1,
          3,
        ),
        onNumberSeconds: envFloat("VITE_VAPI_ENDPOINT_NUMBER_SEC", 1.5),
      },
    },
    stopSpeakingPlan: {
      numWords: envInt("VITE_VAPI_STOP_NUM_WORDS", 4),
      voiceSeconds: envFloat("VITE_VAPI_STOP_VOICE_SEC", 0.45),
      backoffSeconds: envFloat("VITE_VAPI_STOP_BACKOFF_SEC", 1.4),
      acknowledgementPhrases: ["okay", "right", "uh-huh", "yeah", "mm-hmm", "got it", "noted"],
    },
  };
}
