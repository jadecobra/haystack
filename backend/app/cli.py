"""longmuch CLI: health, analyze, contract. JSON on stdout."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx

from app.metrics import LOCKED_LABELS, SCHEMA_VERSION, TREASURY_LABEL, groups_payload
from app.sources import analyze as analyze_local

DEFAULT_BASE = "http://127.0.0.1:8000"


def _dump(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2) + "\n")


def _incomplete(payload: dict[str, Any]) -> str | None:
    rows = payload.get("rows")
    years = payload.get("years")
    if not isinstance(rows, list) or not isinstance(years, list):
        return "missing rows or years"
    labels = [r.get("metric") for r in rows if isinstance(r, dict)]
    if labels != list(LOCKED_LABELS):
        return "metric labels drifted or incomplete"
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, dict):
            return "row missing values"
        for year in years:
            cell = values.get(str(year))
            if cell is None or cell == "":
                return f"incomplete cell {row.get('metric')} {year}"
    return None


def _get(base: str, path: str) -> tuple[int, Any]:
    url = base.rstrip("/") + path
    try:
        response = httpx.get(url, timeout=60.0)
    except httpx.HTTPError as exc:
        _dump({"error": str(exc), "url": url})
        return 1, None
    try:
        body: Any = response.json()
    except ValueError:
        body = {"raw": response.text}
    if response.status_code >= 400:
        _dump({"status_code": response.status_code, "body": body, "url": url})
        return 1, None
    return 0, body


def cmd_health(base: str) -> int:
    code, body = _get(base, "/health")
    if code != 0:
        return 1
    _dump(body)
    if not isinstance(body, dict) or body.get("status") != "healthy":
        return 1
    return 0


def cmd_analyze(
    ticker: str,
    *,
    base: str | None,
    local: bool,
    edgar: bool,
) -> int:
    if local and edgar:
        _dump({"error": "use either --local (fixture) or --edgar (live), not both"})
        return 1
    if local:
        try:
            payload = analyze_local(ticker, prefer_fixture=True)
        except ValueError as exc:
            _dump({"error": str(exc)})
            return 1
        reason = _incomplete(payload)
        _dump(payload)
        return 1 if reason else 0
    if edgar:
        try:
            payload = analyze_local(ticker, prefer_fixture=False)
        except ValueError as exc:
            _dump({"error": str(exc)})
            return 1
        reason = _incomplete(payload)
        _dump(payload)
        return 1 if reason else 0
    if not base:
        base = DEFAULT_BASE
    code, body = _get(base, f"/analyze/{ticker.upper()}")
    if code != 0:
        return 1
    reason = _incomplete(body) if isinstance(body, dict) else "invalid response"
    _dump(body)
    return 1 if reason else 0


def cmd_contract(base: str | None) -> int:
    local = {
        "schema_version": SCHEMA_VERSION,
        "labels": list(LOCKED_LABELS),
        "row_count": len(LOCKED_LABELS),
        "treasury_label": TREASURY_LABEL,
        "groups": groups_payload(),
    }
    if base:
        code, body = _get(base, "/contract")
        if code != 0:
            return 1
        if not isinstance(body, dict):
            _dump({"error": "invalid contract response", "body": body})
            return 1
        remote_labels = body.get("labels")
        drifted = remote_labels != list(LOCKED_LABELS)
        _dump(body)
        return 1 if drifted else 0
    _dump(local)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="longmuch")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_health = sub.add_parser("health")
    p_health.add_argument("--base", default=DEFAULT_BASE)

    p_analyze = sub.add_parser("analyze")
    p_analyze.add_argument("ticker")
    p_analyze.add_argument("--base", default=None)
    p_analyze.add_argument(
        "--local",
        action="store_true",
        help="in-process fixture table (no HTTP; agent/offline path)",
    )
    p_analyze.add_argument(
        "--edgar",
        action="store_true",
        help="in-process live SEC companyfacts + FRED (no HTTP)",
    )

    p_contract = sub.add_parser("contract")
    p_contract.add_argument("--base", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "health":
        return cmd_health(args.base)
    if args.cmd == "analyze":
        return cmd_analyze(
            args.ticker,
            base=args.base,
            local=args.local,
            edgar=args.edgar,
        )
    if args.cmd == "contract":
        return cmd_contract(args.base)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
