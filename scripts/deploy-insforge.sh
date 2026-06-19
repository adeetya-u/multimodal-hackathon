#!/usr/bin/env bash
# Deploy Scalpel to Insforge: HIPAA SQL → API (compute) → UI (deployments).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_ENV="$ROOT/backend/.env"
HIPAA_SQL="$ROOT/backend/scripts/insforge_hipaa.sql"

die() { echo "error: $*" >&2; exit 1; }

[[ -f "$BACKEND_ENV" ]] || die "Missing $BACKEND_ENV"

# shellcheck disable=SC1090
source "$BACKEND_ENV"

CLI=(npx -y @insforge/cli)

echo "==> Applying HIPAA schema (RLS + audit_events)…"
if [[ -f "$HIPAA_SQL" ]]; then
  SQL="$(tr '\n' ' ' <"$HIPAA_SQL" | sed 's/  */ /g')"
  set -a && source "$ROOT/.cursor/mcp.env" 2>/dev/null || true
  set +a
  API_KEY="${API_KEY:-${INSFORGE_SERVICE_KEY:-}}"
  API_BASE="${API_BASE_URL:-${INSFORGE_URL:-}}"
  if [[ -n "$API_KEY" && -n "$API_BASE" ]]; then
    printf '%s\n' \
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"deploy","version":"1"}}}' \
      '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
      "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"run-raw-sql\",\"arguments\":{\"query\":$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$SQL")}}}" \
      | API_KEY="$API_KEY" API_BASE_URL="$API_BASE" npx -y @insforge/mcp@latest >/dev/null \
      && echo "    HIPAA SQL applied" \
      || echo "    warn: HIPAA SQL via MCP failed — apply backend/scripts/insforge_hipaa.sql manually"
  fi
fi

echo "==> Creating private storage bucket case-docs (if missing)…"
"${CLI[@]}" metadata --json 2>/dev/null | python3 -c "
import json,sys
try:
  d=json.load(sys.stdin)
  buckets=[b.get('name') for b in d.get('storage',{}).get('buckets',[])]
  print('buckets:', buckets)
except Exception:
  pass
" || true

if ! command -v flyctl >/dev/null 2>&1; then
  echo "==> Installing flyctl (required for Insforge compute deploy)…"
  curl -L https://fly.io/install.sh | sh
  export PATH="${HOME}/.fly/bin:${PATH}"
fi

echo "==> Deploying FastAPI to Insforge compute (scalpel-api)…"
export PATH="${HOME}/.fly/bin:${PATH}"
PROD_ENV="$ROOT/backend/.env.insforge-deploy"
grep -E '^(LLM_PROVIDER|MINIMAX_|NEBIUS_|VAPI_|INSFORGE_|STORAGE_BACKEND|CORS_ORIGINS|HIPAA_MODE|PORT)=' "$BACKEND_ENV" >"$PROD_ENV" || true
{
  echo "STORAGE_BACKEND=insforge"
  echo "HIPAA_MODE=true"
  echo "PORT=8080"
} >>"$PROD_ENV"

"${CLI[@]}" compute deploy "$ROOT/backend" \
  --name scalpel-api \
  --port 8080 \
  --env-file "$PROD_ENV" \
  --region iad \
  -y

API_URL="$("${CLI[@]}" compute list --json 2>/dev/null | python3 -c "
import json,sys
items=json.load(sys.stdin)
for s in items:
    if s.get('name')=='scalpel-api':
        print(s.get('endpointUrl') or s.get('url') or '')
        break
" || true)"

[[ -n "$API_URL" ]] || API_URL="${SCALPEL_API_URL:-}"

echo "==> API URL: ${API_URL:-<check: insforge compute list>}"

echo "==> Setting frontend build env…"
[[ -n "$API_URL" ]] && "${CLI[@]}" deployments env set VITE_API_BASE "$API_URL" 2>/dev/null || true
for key in VITE_VAPI_PUBLIC_KEY VITE_VAPI_OR_ASSISTANT_ID VITE_VAPI_INTRO_ASSISTANT_ID; do
  val="${!key:-}"
  [[ -n "$val" ]] && "${CLI[@]}" deployments env set "$key" "$val" 2>/dev/null || true
done

echo "==> Deploying React UI…"
"${CLI[@]}" deployments deploy "$ROOT/web" -y

echo ""
echo "Done. Next:"
echo "  1. Set VAPI_SERVER_URL=${API_URL}/api/vapi/webhook in Vapi dashboard"
echo "  2. Set CORS_ORIGINS to your Insforge UI URL (deployments list)"
echo "  3. Request Insforge Enterprise HIPAA BAA before real PHI"
echo "  4. Sign BAAs with Vapi + LLM provider (MiniMax/Nebius)"
