#!/usr/bin/env bash
# Scalpel — API + web UI (Vapi voice via cloud webhooks; no local voice worker).
#
#   ./dev.sh         start API + UI
#   ./dev.sh stop    stop services
#   ./dev.sh seed    seed demo case-001

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
WEB="$ROOT/web"
RUN_DIR="$ROOT/.run"
STATE_FILE="$RUN_DIR/dev.state"

API_PORT="${SCALPEL_API_PORT:-3001}"
UI_PORT="${SCALPEL_UI_PORT:-5173}"

export PYTHONPATH="$BACKEND"

port_pids() { lsof -ti ":$1" 2>/dev/null || true; }
pid_alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }

load_env() {
  set -a
  [ -f "$BACKEND/.env" ] && source "$BACKEND/.env"
  [ -f "$ROOT/.env" ] && source "$ROOT/.env"
  set +a
}

ensure_deps() {
  [ -d "$BACKEND/.venv" ] || (cd "$BACKEND" && uv sync)
  [ -d "$WEB/node_modules" ] || (cd "$WEB" && npm install)
}

write_state() {
  mkdir -p "$RUN_DIR"
  printf '{"api_pid":%s,"ui_pid":%s,"api_port":%s,"ui_port":%s}\n' \
    "$1" "$2" "$API_PORT" "$UI_PORT" >"$STATE_FILE"
}

cmd_stop() {
  local state api_pid ui_pid
  state="$(cat "$STATE_FILE" 2>/dev/null || true)"
  if [ -n "$state" ]; then
    api_pid="$(printf '%s' "$state" | sed -n 's/.*"api_pid":\([0-9][0-9]*\).*/\1/p')"
    ui_pid="$(printf '%s' "$state" | sed -n 's/.*"ui_pid":\([0-9][0-9]*\).*/\1/p')"
    pid_alive "$api_pid" && kill "$api_pid" 2>/dev/null || true
    pid_alive "$ui_pid" && kill "$ui_pid" 2>/dev/null || true
  fi
  port_pids "$API_PORT" | xargs kill -9 2>/dev/null || true
  port_pids "$UI_PORT" | xargs kill -9 2>/dev/null || true
  rm -f "$STATE_FILE"
  echo "Stopped Scalpel stack."
}

cmd_start() {
  if [ -n "$(port_pids "$API_PORT")" ] || [ -n "$(port_pids "$UI_PORT")" ]; then
    echo "Ports in use. Run ./dev.sh stop first." >&2
    exit 1
  fi
  ensure_deps
  load_env
  mkdir -p "$RUN_DIR"
  trap 'kill $(jobs -pr) 2>/dev/null || true; rm -f "$STATE_FILE"' EXIT INT TERM

  echo "Starting API on :$API_PORT …"
  (cd "$BACKEND" && uv run python services/api/main.py) &
  local api_pid=$!

  echo "Starting UI on :$UI_PORT …"
  (cd "$WEB" && npm run dev) &
  local ui_pid=$!

  write_state "$api_pid" "$ui_pid"
  echo ""
  echo "  API  http://localhost:${API_PORT}"
  echo "  UI   http://localhost:${UI_PORT}/prep"
  echo ""
  echo "  Vapi webhooks: set VAPI_SERVER_URL to your ngrok URL"
  echo "  Stop: ./dev.sh stop"
  echo ""
  wait
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status)
    echo "API :$API_PORT → $(port_pids "$API_PORT" | tr '\n' ' ')"
    echo "UI  :$UI_PORT → $(port_pids "$UI_PORT" | tr '\n' ' ')"
    ;;
  restart) cmd_stop; cmd_start ;;
  seed)
    load_env
    if [ "${STORAGE_BACKEND:-filesystem}" = "insforge" ]; then
      (cd "$BACKEND" && PYTHONPATH=. uv run python scripts/seed_insforge_demo.py)
    else
      (cd "$BACKEND" && PYTHONPATH=. uv run python scripts/seed_demo_case.py)
    fi
    ;;
  *) echo "Usage: $0 {start|stop|status|restart|seed}" >&2; exit 1 ;;
esac
