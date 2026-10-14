"""S&P 500 peers by GICS (#42).

Rule (checkable, no guesses): peers are the other S&P 500 names in the same
GICS sub-industry (``data/sp500_tickers.json``). If that leaves fewer than
``MIN_PEERS``, widen to the GICS industry group (``data/gics_structure.json``);
same-sub-industry names stay first. Sorted by ticker within each tier, capped
at ``MAX_PEERS``. Non-S&P tickers get no peers.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.classification import load_gics

STRUCTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "gics_structure.json"
MIN_PEERS = 3
MAX_PEERS = 40


@lru_cache(maxsize=1)
def load_structure() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(STRUCTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    subs = raw.get("sub_industries") if isinstance(raw, dict) else None
    return subs if isinstance(subs, dict) else {}


def _names() -> dict[str, str]:
    try:
        from app.screen import load_snapshot

        snap = load_snapshot() or {}
    except Exception:  # noqa: BLE001 - names are cosmetic
        return {}
    return {
        str(r.get("ticker")).upper(): r["name"]
        for r in snap.get("rows") or []
        if isinstance(r, dict) and r.get("ticker") and isinstance(r.get("name"), str)
    }


def peers_for(
    ticker: str,
    *,
    gics: dict[str, dict[str, Any]] | None = None,
    structure: dict[str, dict[str, str]] | None = None,
    names: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    gics = load_gics() if gics is None else gics
    structure = load_structure() if structure is None else structure
    symbol = ticker.upper().strip()
    me = gics.get(symbol) or gics.get(symbol.replace("-", ".")) or gics.get(symbol.replace(".", "-"))
    sub = (me or {}).get("sub_industry")
    if not sub:
        return None
    # Canonical (dotted) tickers only; load_gics also indexes dash aliases.
    universe = {t: g for t, g in gics.items() if "-" not in t}
    self_keys = {symbol, symbol.replace("-", "."), symbol.replace(".", "-")}
    same = sorted(t for t, g in universe.items() if g.get("sub_industry") == sub and t not in self_keys)
    basis, group = "sub_industry", sub
    chosen = list(same)
    group_info = structure.get(sub) or {}
    if len(same) < MIN_PEERS and group_info.get("industry_group"):
        ig = group_info["industry_group"]
        wider = sorted(
            t
            for t, g in universe.items()
            if t not in self_keys
            and t not in same
            and (structure.get(g.get("sub_industry") or "") or {}).get("industry_group") == ig
        )
        chosen = same + wider
        basis, group = "industry_group", ig
    names = _names() if names is None else names
    return {
        "basis": basis,
        "group": group,
        "sub_industry": sub,
        "fallback": basis != "sub_industry",
        "total": len(chosen),
        "peers": [{"ticker": t, "name": names.get(t)} for t in chosen[:MAX_PEERS]],
    }
