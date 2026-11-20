#!/usr/bin/env bash
# Start a local API and a production Next server, then run the click-through.
# The preview job and a laptop use this same script. Ports 3000 and 8000 stay untouched.
set -euo pipefail

say() { printf '%s\n' "$1"; }

fp="${CLICK_FRONTEND_PORT:-3466}"
bp="${CLICK_BACKEND_PORT:-8021}"
if [ "$fp" = "3000" ] || [ "$bp" = "8000" ]; then
  say "click-through FAIL path=setup width=0 problem=refusing port 3000 or 8000"
  exit 1
fi

root="$(cd "$(dirname "$0")/../.." && pwd)"
here="$(cd "$(dirname "$0")" && pwd)"
export CLICK_ORIGIN="http://127.0.0.1:${fp}"
export CLICK_OUT_DIR="${CLICK_OUT_DIR:-$here/artifacts}"
unset HAYSTACK_PREFER_FIXTURE || true

port_busy() {
  python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
sock = socket.socket()
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    sys.exit(0)
finally:
    sock.close()
sys.exit(1)
PY
}

if port_busy "$fp" || port_busy "$bp"; then
  say "click-through FAIL path=setup width=0 problem=port ${fp} or ${bp} is already in use"
  exit 1
fi

be_pid=""
fe_pid=""
log_dir="$(mktemp -d /tmp/click-through-logs.XXXXXX)"

spawn_group() {
  local dir="$1" log="$2"
  shift 2
  python3 -c 'import os, sys; os.chdir(sys.argv[1]); os.setsid(); os.execvp(sys.argv[2], sys.argv[2:])' "$dir" "$@" >"$log" 2>&1 &
}

kill_group() {
  local pgid="$1"
  [ -n "$pgid" ] || return 0
  kill -TERM -- "-$pgid" >/dev/null 2>&1 || kill -TERM "$pgid" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    if ! kill -0 -- "-$pgid" >/dev/null 2>&1 && ! kill -0 "$pgid" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  kill -KILL -- "-$pgid" >/dev/null 2>&1 || kill -KILL "$pgid" >/dev/null 2>&1 || true
}

cleanup() {
  kill_group "$fe_pid"
  kill_group "$be_pid"
  rm -rf "$log_dir"
}
trap cleanup EXIT
mkdir -p "$CLICK_OUT_DIR"

spawn_group "$root/backend" "$log_dir/backend.log" uv run uvicorn app.main:app --host 127.0.0.1 --port "$bp"
be_pid=$!

ready=0
for _ in $(seq 1 180); do
  if curl -sf "http://127.0.0.1:${bp}/health" >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$be_pid" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  say "click-through FAIL path=setup width=0 problem=backend did not become ready"
  tail -n 40 "$log_dir/backend.log" || true
  exit 1
fi

if ! (
  cd "$root/frontend"
  if [ ! -x node_modules/.bin/next ]; then
    pnpm install --frozen-lockfile
  fi
  BACKEND_ORIGIN="http://127.0.0.1:${bp}" pnpm exec next build
) >"$log_dir/frontend.log" 2>&1; then
  say "click-through FAIL path=setup width=0 problem=frontend build failed"
  tail -n 40 "$log_dir/frontend.log" || true
  exit 1
fi

spawn_group "$root/frontend" "$log_dir/frontend.log" env BACKEND_ORIGIN="http://127.0.0.1:${bp}" pnpm exec next start --hostname 127.0.0.1 --port "$fp"
fe_pid=$!

ready=0
for _ in $(seq 1 180); do
  if curl -sf "$CLICK_ORIGIN/" >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$fe_pid" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  say "click-through FAIL path=setup width=0 problem=frontend did not become ready"
  tail -n 40 "$log_dir/frontend.log" || true
  exit 1
fi

cd "$here"
if [ ! -d node_modules/playwright ]; then
  npm ci --ignore-scripts --no-audit --no-fund
fi
if [ "${CLICK_SKIP_PLAYWRIGHT_INSTALL:-0}" != "1" ]; then
  if [ "$(uname -s)" = "Linux" ]; then
    npx playwright install --with-deps chromium
  else
    npx playwright install chromium
  fi
fi
set +e
node "$here/browser.cjs" click-through
code=$?
set -e
if [ "$code" -ne 0 ]; then
  say "click-through failed (exit ${code})"
  exit "$code"
fi
exit 0
