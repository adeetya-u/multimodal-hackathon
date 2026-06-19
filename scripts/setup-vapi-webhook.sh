#!/usr/bin/env bash
# Point Scalpel Vapi assistants at your public API webhook + clinical STT.
# OR assistant gets the webhook; intro demo assistant is client-driven (no webhook).
# Usage: ./scripts/setup-vapi-webhook.sh https://your-tunnel.example.com
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_ENV="$ROOT/backend/.env"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <public-api-base-url>" >&2
  echo "Example: $0 https://abc123.ngrok-free.app" >&2
  exit 1
fi

BASE="${1%/}"
WEBHOOK="${BASE}/api/vapi/webhook"

# shellcheck disable=SC1090
source "$BACKEND_ENV"
: "${VAPI_PRIVATE_KEY:?Set VAPI_PRIVATE_KEY in backend/.env}"

TRANSCRIBER_MODEL="${VAPI_TRANSCRIBER_MODEL:-nova-3-medical}"
ENDPOINTING_MS="${VAPI_TRANSCRIBER_ENDPOINTING_MS:-500}"
NO_PUNCT_SEC="${VAPI_ENDPOINT_NO_PUNCT_SEC:-2.8}"
PUNCT_SEC="${VAPI_ENDPOINT_PUNCT_SEC:-0.35}"
NUMBER_SEC="${VAPI_ENDPOINT_NUMBER_SEC:-1.2}"
START_WAIT_SEC="${VAPI_START_WAIT_SEC:-0.5}"
STOP_NUM_WORDS="${VAPI_STOP_NUM_WORDS:-3}"
STOP_VOICE_SEC="${VAPI_STOP_VOICE_SEC:-0.35}"
STOP_BACKOFF_SEC="${VAPI_STOP_BACKOFF_SEC:-1.2}"

OR_ASSISTANT_PATCH=$(python3 - <<PY
import json
print(json.dumps({
  "name": "Scalpel OR",
  "server": {"url": "${WEBHOOK}"},
  "transcriber": {
    "provider": "deepgram",
    "model": "${TRANSCRIBER_MODEL}",
    "language": "en",
    "endpointing": int("${ENDPOINTING_MS}"),
    "fallbackPlan": {"autoFallback": {"enabled": True}},
  },
  "startSpeakingPlan": {
    "waitSeconds": float("${START_WAIT_SEC}"),
    "transcriptionEndpointingPlan": {
      "onPunctuationSeconds": float("${PUNCT_SEC}"),
      "onNoPunctuationSeconds": float("${NO_PUNCT_SEC}"),
      "onNumberSeconds": float("${NUMBER_SEC}"),
    },
  },
  "stopSpeakingPlan": {
    "numWords": int("${STOP_NUM_WORDS}"),
    "voiceSeconds": float("${STOP_VOICE_SEC}"),
    "backoffSeconds": float("${STOP_BACKOFF_SEC}"),
    "acknowledgementPhrases": ["okay", "right", "uh-huh", "yeah", "mm-hmm", "got it", "noted"],
  },
  "firstMessage": (
    "Scalpel is ready. Report a checklist step or ask a clinical question."
  ),
  "model": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "messages": [{
      "role": "system",
      "content": (
        "You are Scalpel, the OR voice assistant. The surgical case is already loaded — "
        "never ask for patient ID, case ID, chart upload, or case setup.\\n\\n"
        "Patient ID: {{patient_id}}\\n"
        "Procedure: {{procedure}}\\n"
        "Operative checklist: {{checklist_summary}}\\n\\n"
        "- When the surgeon asks a clinical question, respond ONLY with Checking. or One moment. "
        "Never answer clinically yourself.\\n"
        "- Do not invent clinical facts or deny/affirm allergies from memory."
      ),
    }],
  },
}))
PY
)

INTRO_ASSISTANT_PATCH=$(python3 - <<PY
import json
print(json.dumps({
  "name": "Scalpel Intro",
  "server": None,
  "transcriber": {
    "provider": "deepgram",
    "model": "${TRANSCRIBER_MODEL}",
    "language": "en",
    "endpointing": int("${ENDPOINTING_MS}"),
    "fallbackPlan": {"autoFallback": {"enabled": True}},
  },
  "startSpeakingPlan": {
    "waitSeconds": float("${START_WAIT_SEC}"),
    "transcriptionEndpointingPlan": {
      "onPunctuationSeconds": float("${PUNCT_SEC}"),
      "onNoPunctuationSeconds": float("${NO_PUNCT_SEC}"),
      "onNumberSeconds": float("${NUMBER_SEC}"),
    },
  },
  "stopSpeakingPlan": {
    "numWords": int("${STOP_NUM_WORDS}"),
    "voiceSeconds": float("${STOP_VOICE_SEC}"),
    "backoffSeconds": float("${STOP_BACKOFF_SEC}"),
    "acknowledgementPhrases": ["okay", "right", "uh-huh", "yeah", "mm-hmm", "got it", "noted"],
  },
  "firstMessage": (
    "Hi, I'm Scalpel. Ask anything about knee surgery!"
  ),
  "model": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "messages": [{
      "role": "system",
      "content": (
        "You are Scalpel on the public knee surgery demo. There is NO patient chart.\\n\\n"
        "- For greetings or meta questions, reply in one short sentence. "
        "Mention general knee questions or continuing to prep for a full case.\\n"
        "- For ANY clinical question, respond ONLY with Let me look that up. "
        "Never answer clinically yourself.\\n"
        "- Never say Checking., One moment., or ask for patient ID or chart upload.\\n"
        "- Do not invent clinical facts."
      ),
    }],
  },
}))
PY
)

patch_assistant() {
  local id="$1"
  local patch="$2"
  local label="$3"
  echo "Updating ${label} assistant ${id}"
  curl -sS -X PATCH "https://api.vapi.ai/assistant/${id}" \
    -H "Authorization: Bearer ${VAPI_PRIVATE_KEY}" \
    -H "Content-Type: application/json" \
    -d "$patch" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','?'), '→', (d.get('server') or {}).get('url','(no webhook)'), '|', d.get('transcriber',{}).get('model','?'))"
}

if [[ -n "${VAPI_OR_ASSISTANT_ID:-}" ]]; then
  patch_assistant "$VAPI_OR_ASSISTANT_ID" "$OR_ASSISTANT_PATCH" "OR"
fi

if [[ -n "${VAPI_INTRO_ASSISTANT_ID:-}" ]]; then
  patch_assistant "$VAPI_INTRO_ASSISTANT_ID" "$INTRO_ASSISTANT_PATCH" "intro demo"
fi

if grep -q '^VAPI_SERVER_URL=' "$BACKEND_ENV"; then
  if [[ "$(uname)" == Darwin ]]; then
    sed -i '' "s|^VAPI_SERVER_URL=.*|VAPI_SERVER_URL=${BASE}|" "$BACKEND_ENV"
  else
    sed -i "s|^VAPI_SERVER_URL=.*|VAPI_SERVER_URL=${BASE}|" "$BACKEND_ENV"
  fi
else
  echo "VAPI_SERVER_URL=${BASE}" >>"$BACKEND_ENV"
fi

echo ""
echo "Done. VAPI_SERVER_URL=${BASE}"
echo "OR webhook: ${WEBHOOK}"
echo "Intro demo: no server webhook (answers via /api/intro/utterance)"
echo "Restart ./dev.sh after changing backend/.env"
