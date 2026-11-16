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
cleanup() {
  if [ -n "$fe_pid" ]; then kill "$fe_pid" >/dev/null 2>&1 || true; fi
  if [ -n "$be_pid" ]; then kill "$be_pid" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
mkdir -p "$CLICK_OUT_DIR"

(
  cd "$root/backend"
  uv run uvicorn app.main:app --host 127.0.0.1 --port "$bp"
) >"$log_dir/backend.log" 2>&1 &
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

(
  cd "$root/frontend"
  if [ ! -x node_modules/.bin/next ]; then
    pnpm install --frozen-lockfile
  fi
  BACKEND_ORIGIN="http://127.0.0.1:${bp}" pnpm exec next build
  BACKEND_ORIGIN="http://127.0.0.1:${bp}" pnpm exec next start --hostname 127.0.0.1 --port "$fp"
) >"$log_dir/frontend.log" 2>&1 &
fe_pid=$!

ready=0
for _ in $(seq 1 180); do
  if curl -sf "$CLICK_ORIGIN/" >/dev/null; then
    ready=1
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
  npm install --ignore-scripts --no-audit --no-fund
fi
if [ "$(uname -s)" = "Linux" ]; then
  npx playwright install --with-deps chromium
else
  npx playwright install chromium
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
