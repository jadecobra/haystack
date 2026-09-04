#!/usr/bin/env bash
# Shared helpers for verify-haystack. Sourced by launch/doctor/cleanup/http.
# Not a user-facing entrypoint.

set -euo pipefail

_THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$_THIS_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/../../.." && pwd)"
ARTIFACTS_DIR="$SKILL_DIR/artifacts"
CURRENT_RUN_FILE="$SKILL_DIR/.current-run"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_DIR="$REPO_ROOT/backend"

FORBIDDEN_FRONTEND_PORTS="3000"
FORBIDDEN_BACKEND_PORTS="8000"
PREFERRED_FRONTEND_PORTS="3457 3458 3459 3460 3461 3462 3463 3464"
PREFERRED_BACKEND_PORTS="8015 8016 8017 8018 8019 8020 8021 8022"

die() {
  echo "verify-haystack: $*" >&2
  exit 1
}

port_from_origin() {
  local origin="${1:-}"
  local rest="${origin##*://}"
  rest="${rest%%/*}"
  if [[ "$rest" == *:* ]]; then
    echo "${rest##*:}"
  else
    echo ""
  fi
}

refuse_frontend_port() {
  local port="${1:-}"
  case " $FORBIDDEN_FRONTEND_PORTS " in
    *" $port "*)
      die "refusing frontend port $port. README/ao default is :3000 (agent orchestrator and Next default). Launch an isolated frontend with helpers/launch (ports 3457-3464)."
      ;;
  esac
}

refuse_backend_port() {
  local port="${1:-}"
  case " $FORBIDDEN_BACKEND_PORTS " in
    *" $port "*)
      die "refusing backend port $port. README default is uvicorn --port 8000 and other gym projects already bind it. Launch an isolated backend with helpers/launch (ports 8015-8022)."
      ;;
  esac
}

refuse_frontend_origin() {
  local origin="${1:-}"
  local port
  port="$(port_from_origin "$origin")"
  [[ -n "$port" ]] || die "frontend origin has no explicit port: $origin"
  refuse_frontend_port "$port"
  if [[ "$origin" == *"localhost:3000"* ]] || [[ "$origin" == *"127.0.0.1:3000"* ]]; then
    die "refusing shared frontend origin $origin"
  fi
}

refuse_backend_origin() {
  local origin="${1:-}"
  local port
  port="$(port_from_origin "$origin")"
  [[ -n "$port" ]] || die "backend origin has no explicit port: $origin"
  refuse_backend_port "$port"
  if [[ "$origin" == *"localhost:8000"* ]] || [[ "$origin" == *"127.0.0.1:8000"* ]]; then
    die "refusing shared backend origin $origin"
  fi
}

lsof_listen_pid() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2; exit}'
}

lsof_listen_cmd() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1; exit}'
}

port_is_free() {
  local port="$1"
  [[ -z "$(lsof_listen_pid "$port")" ]]
}

pick_port_from() {
  local p
  for p in $1; do
    if port_is_free "$p"; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

pick_frontend_port() {
  local p
  p="$(pick_port_from "$PREFERRED_FRONTEND_PORTS" || true)"
  [[ -n "$p" ]] || die "no free frontend isolation port in $PREFERRED_FRONTEND_PORTS"
  echo "$p"
}

pick_backend_port() {
  local p
  p="$(pick_port_from "$PREFERRED_BACKEND_PORTS" || true)"
  [[ -n "$p" ]] || die "no free backend isolation port in $PREFERRED_BACKEND_PORTS"
  echo "$p"
}

snapshot_listen() {
  local port="$1"
  local pid cmd
  pid="$(lsof_listen_pid "$port" || true)"
  cmd="$(lsof_listen_cmd "$port" || true)"
  echo "port=${port} pid=${pid:-none} cmd=${cmd:-none}"
}

pid_is_descendant_of() {
  local child="$1"
  local ancestor="$2"
  local walk="$child"
  local i
  [[ -n "$child" && -n "$ancestor" ]] || return 1
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    [[ "$walk" == "$ancestor" ]] && return 0
    walk="$(ps -o ppid= -p "$walk" 2>/dev/null | tr -d ' ' || true)"
    [[ -z "$walk" || "$walk" == "1" || "$walk" == "0" ]] && return 1
  done
  return 1
}

listen_owned_by() {
  local listen_pid="$1"
  local recorded="$2"
  [[ -n "$listen_pid" && -n "$recorded" ]] || return 1
  [[ "$listen_pid" == "$recorded" ]] && return 0
  pid_is_descendant_of "$listen_pid" "$recorded"
}

load_run() {
  local run_id="${RUN_ID:-}"
  local run_dir=""
  if [[ -n "$run_id" ]]; then
    run_dir="/tmp/haystack-verify-$run_id"
  elif [[ -f "$CURRENT_RUN_FILE" ]]; then
    run_dir="$(cat "$CURRENT_RUN_FILE")"
  else
    die "no RUN_ID and no $CURRENT_RUN_FILE. Run helpers/launch first."
  fi
  [[ -d "$run_dir" ]] || die "run dir missing: $run_dir"
  [[ -f "$run_dir/run.env" ]] || die "run.env missing in $run_dir"
  set -a
  # shellcheck disable=SC1090
  source "$run_dir/run.env"
  set +a
  RUN_DIR="$run_dir"
  refuse_frontend_port "$FRONTEND_PORT"
  refuse_frontend_origin "$FRONTEND_ORIGIN"
  if [[ -n "${BACKEND_PORT:-}" && "${BACKEND_OK:-0}" == "1" ]]; then
    refuse_backend_port "$BACKEND_PORT"
    refuse_backend_origin "$BACKEND_ORIGIN"
  fi
}

html_count() {
  local file="$1"
  local needle="$2"
  python3 - "$file" "$needle" <<'PY'
import sys
path, needle = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8", errors="replace").read()
print(text.count(needle))
PY
}

html_title() {
  local file="$1"
  python3 - "$file" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
print(m.group(1).strip() if m else "")
PY
}

html_h1() {
  local file="$1"
  python3 - "$file" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
print(re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "")
PY
}

html_placeholder() {
  local file="$1"
  python3 - "$file" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r'<input[^>]*placeholder="([^"]+)"', text, re.I)
print(m.group(1) if m else "")
PY
}

html_button_text() {
  local file="$1"
  python3 - "$file" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"<button[^>]*>(.*?)</button>", text, re.I | re.S)
print(re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "")
PY
}

button_is_disabled() {
  local file="$1"
  python3 - "$file" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"<button\b[^>]*>", text, re.I)
if not m:
    print("missing")
    raise SystemExit
tag = m.group(0)
print("yes" if re.search(r"\bdisabled\b", tag, re.I) else "no")
PY
}
