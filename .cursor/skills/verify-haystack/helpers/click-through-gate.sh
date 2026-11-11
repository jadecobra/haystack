#!/usr/bin/env bash
# Decide the click-through / preview job. Never prints secret values.
# GATE_SIMULATE=secret-missing|no-preview|timeout|click-fail
# runs the decision without GitHub. Otherwise this is the Actions entry.
set -euo pipefail

say() { printf '%s\n' "$1"; }

if [ "${GATE_SIMULATE:-}" = "timeout" ]; then
  say "click-through timed out waiting for a Vercel preview"
  exit 1
fi

if [ "${GATE_SIMULATE:-}" = "click-fail" ]; then
  say "click-through path=analyze width=390 result=fail problem=request /api/analyze/AAPL status 500"
  exit 1
fi

if [ "${GATE_SIMULATE:-}" = "no-preview" ]; then
  say "no preview: skipped"
  exit 0
fi

secret="${VERCEL_AUTOMATION_BYPASS_SECRET:-}"
if [ -z "$secret" ] || [ "${GATE_SIMULATE:-}" = "secret-missing" ]; then
  say "click-through skipped: VERCEL protection bypass secret is not set"
  exit 0
fi

if [ -n "${GATE_SIMULATE:-}" ]; then
  say "unknown GATE_SIMULATE"
  exit 1
fi

event="${EVENT_NAME:-}"
repo="${GITHUB_REPOSITORY:-}"
sha=""
preview_url=""

if [ "$event" = "deployment_status" ]; then
  sha="${DEPLOYMENT_SHA:-}"
  state="${DEPLOYMENT_STATE:-}"
  env_name="${DEPLOYMENT_ENV:-}"
  preview_url="${DEPLOYMENT_URL:-}"
  if ! printf '%s' "$env_name" | grep -qi preview; then
    say "click-through skipped: deployment environment is not a preview"
    exit 0
  fi
  case "$state" in
    success)
      if [ -z "$preview_url" ]; then
        say "click-through FAIL: deployment succeeded without a preview url"
        exit 1
      fi
      ;;
    failure|error)
      say "click-through FAIL: Vercel preview deployment ${state}"
      exit 1
      ;;
    *)
      say "click-through skipped: deployment state ${state:-unknown} is not success"
      exit 0
      ;;
  esac
else
  sha="${PR_SHA:-${GITHUB_SHA:-}}"
  if [ -z "$repo" ] || [ -z "$sha" ]; then
    say "click-through FAIL: missing repository or sha"
    exit 1
  fi
  deadline=$((SECONDS + 180))
  saw_deployment=0
  while [ "$SECONDS" -lt "$deadline" ]; do
    ids="$(gh api "repos/${repo}/deployments?sha=${sha}" --jq '.[] | select(.environment|test("preview";"i")) | .id' 2>/dev/null || true)"
    if [ -n "$ids" ]; then
      saw_deployment=1
      for id in $ids; do
        line="$(gh api "repos/${repo}/deployments/${id}/statuses" --jq '.[0] | [.state, (.environment_url // "")] | @tsv' 2>/dev/null || true)"
        st="${line%%$'\t'*}"
        url="${line#*$'\t'}"
        if [ "$st" = "success" ] && [ -n "$url" ] && [ "$url" != "$st" ]; then
          preview_url="$url"
          break
        fi
        if [ "$st" = "failure" ] || [ "$st" = "error" ]; then
          say "click-through FAIL: Vercel preview deployment ${st}"
          exit 1
        fi
      done
    fi
    if [ -n "$preview_url" ]; then
      break
    fi
    sleep 15
  done
  if [ -z "$preview_url" ]; then
    if [ "$saw_deployment" -eq 1 ]; then
      say "click-through timed out waiting for a Vercel preview"
      exit 1
    fi
    say "no preview: skipped"
    exit 0
  fi
fi

root="$(cd "$(dirname "$0")/../../../.." && pwd)"
export CLICK_ORIGIN="$preview_url"
export CLICK_OUT_DIR="${CLICK_OUT_DIR:-$root/.cursor/skills/verify-haystack/artifacts/click-through}"
cd "$root/.cursor/skills/verify-haystack"
if [ ! -d node_modules/playwright ]; then
  npm install --ignore-scripts --no-audit --no-fund
fi
npx playwright install --with-deps chromium
set +e
node "$root/.cursor/skills/verify-haystack/helpers/browser.cjs" click-through
code=$?
set -e
if [ "$code" -ne 0 ]; then
  say "click-through failed (exit ${code})"
  exit "$code"
fi
exit 0
