#!/usr/bin/env bash
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
exec bash "$root/scripts/click-through/click-through-gate.sh" "$@"
