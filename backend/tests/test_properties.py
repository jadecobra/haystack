"""Property-based tests for owner earnings, metrics, payback, and EDGAR normalization."""

from __future__ import annotations

import copy
import math
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.edgar import _owner_earnings, apply_market_splits, fiscal_year_label
from app.metrics import (
    CLOSE_YIELD_LABELS,
    LOCKED_GROUPS,
    LOCKED_LABELS,
    PERCENT_LABELS,
    TREASURY_LABEL,
    build_table,
    compute_year,
    format_cell,
)
from app.payback import (
    average_oe,
    build_payback,
    conservative_pair,
    payback_years,
    treasury_payback_years,
)
from app.quote import Split

DOLLAR_FIELDS = (
    "revenue",
    "net_income",
    "equity",
    "assets",
    "total_liabilities",
    "debt",
    "owner_earnings",
    "dividends",
    "cash",
)

PER_SHARE_LABELS = tuple(
    next(group["labels"] for group in LOCKED_GROUPS if group["id"] == "per_share")
)

_FINITE_AMOUNT = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)
_NONZERO_MAGNITUDE = st.floats(
    min_value=1e-2,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)
_SIGNED_NONZERO_OR_NONE = st.one_of(
    st.none(),
    st.just(0.0),
    _NONZERO_MAGNITUDE,
    _NONZERO_MAGNITUDE.map(lambda x: -x),
)
_POSITIVE_SHARES = st.floats(
    min_value=1.0,
    max_value=1e12,
    allow_nan=False,
    allow_infinity=False,
)
_POSITIVE_PRICE = st.floats(
    min_value=0.01,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
)
_POSITIVE_RATE = st.floats(
    min_value=1e-4,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)
_POSITIVE_SCALE = st.floats(
    min_value=1e-3,
    max_value=1e3,
    allow_nan=False,
    allow_infinity=False,
)
_SPLIT_RATIO = st.floats(
    min_value=0.05,
    max_value=50.0,
    allow_nan=False,
    allow_infinity=False,
)
_YEAR = st.integers(min_value=2010, max_value=2030)
_YEAR_DICT = st.dictionaries(_YEAR, _FINITE_AMOUNT, max_size=8)


def _assert_close_or_both_none(
    actual: float | None,
    expected: float | None,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-9,
) -> None:
    if expected is None:
        assert actual is None
        return
    assert actual is not None
    assert math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol)


@settings(deadline=None, max_examples=100)
@given(ocf=_YEAR_DICT, capex=_YEAR_DICT, da=_YEAR_DICT)
def test_owner_earnings_leg_selection_and_bounds(
    ocf: dict[int, float],
    capex: dict[int, float],
    da: dict[int, float],
) -> None:
    result = _owner_earnings(ocf, capex, da)
    assert set(result) <= set(ocf)
    for year, ocf_val in ocf.items():
        has_capex = year in capex
        has_da = year in da
        if has_capex and has_da:
            assert result[year] == ocf_val - min(capex[year], da[year])
            assert result[year] >= ocf_val - max(capex[year], da[year])
        elif has_capex:
            assert result[year] == ocf_val - capex[year]
        elif has_da:
            assert result[year] == ocf_val - da[year]
        else:
            assert year not in result


@settings(deadline=None, max_examples=100)
@given(ocf=_YEAR_DICT, capex=_YEAR_DICT, da=_YEAR_DICT, delta=_FINITE_AMOUNT)
def test_owner_earnings_shift_linearity(
    ocf: dict[int, float],
    capex: dict[int, float],
    da: dict[int, float],
    delta: float,
) -> None:
    baseline = _owner_earnings(ocf, capex, da)
    shifted = _owner_earnings({y: v + delta for y, v in ocf.items()}, capex, da)
    assert set(shifted) == set(baseline)
    for year, base_oe in baseline.items():
        maint = min(capex[year], da[year]) if (year in capex and year in da) else capex.get(year, da.get(year, 0.0))
        scale = max(1.0, abs(ocf[year]), abs(delta), abs(maint))
        assert math.isclose(
            shifted[year],
            base_oe + delta,
            rel_tol=1e-9,
            abs_tol=1e-9 * scale,
        )


@st.composite
def _statement_dict(draw: st.DrawFn, *, allow_dps_override: bool = False) -> dict[str, float | None]:
    stmt: dict[str, float | None] = {
        field: draw(_SIGNED_NONZERO_OR_NONE) for field in DOLLAR_FIELDS
    }
    stmt["shares"] = draw(st.one_of(st.none(), st.just(0.0), _POSITIVE_SHARES))
    if allow_dps_override:
        stmt["dividends_per_share"] = draw(st.one_of(st.none(), _POSITIVE_PRICE))
    return stmt


@settings(deadline=None, max_examples=100)
@given(
    years=st.lists(_YEAR, min_size=0, max_size=6, unique=True),
    data=st.data(),
    treasury_yield=st.one_of(st.none(), st.just(0.0), _POSITIVE_RATE),
    previous_close=st.one_of(st.none(), st.just(0.0), _POSITIVE_PRICE),
)
def test_compute_year_and_build_table_contract(
    years: list[int],
    data: st.DataObject,
    treasury_yield: float | None,
    previous_close: float | None,
) -> None:
    statements = {
        year: data.draw(_statement_dict(allow_dps_override=True)) for year in years
    }
    single = compute_year(
        statements[years[0]] if years else {},
        treasury_yield,
        previous_close,
    )
    assert set(single) == set(LOCKED_LABELS)

    treasury_by_year = (
        {year: treasury_yield for year in years}
        if treasury_yield is not None
        else None
    )
    table = build_table(years, statements, treasury_by_year, previous_close)
    assert len(table) == len(LOCKED_LABELS)
    assert [row["metric"] for row in table] == LOCKED_LABELS


@settings(deadline=None, max_examples=100)
@given(
    stmt=_statement_dict(allow_dps_override=False),
    scale=_POSITIVE_SCALE,
    treasury_yield=st.one_of(st.none(), _POSITIVE_RATE),
    previous_close=st.one_of(st.none(), _POSITIVE_PRICE),
)
def test_metrics_scale_invariance(
    stmt: dict[str, float | None],
    scale: float,
    treasury_yield: float | None,
    previous_close: float | None,
) -> None:
    scaled_stmt = dict(stmt)
    for field in DOLLAR_FIELDS:
        val = stmt[field]
        if val is not None:
            scaled_stmt[field] = val * scale

    before = compute_year(stmt, treasury_yield, previous_close)
    after = compute_year(scaled_stmt, treasury_yield, previous_close)

    for label in PERCENT_LABELS:
        _assert_close_or_both_none(after[label], before[label])

    for label in PER_SHARE_LABELS:
        before_val = before[label]
        expected = None if before_val is None else before_val * scale
        _assert_close_or_both_none(after[label], expected)

    before_treasury = before[TREASURY_LABEL]
    expected_treasury = None if before_treasury is None else before_treasury * scale
    _assert_close_or_both_none(after[TREASURY_LABEL], expected_treasury)


@settings(deadline=None, max_examples=100)
@given(
    stmt=_statement_dict(allow_dps_override=True),
    factor=_POSITIVE_SCALE,
    treasury_yield=st.one_of(st.none(), _POSITIVE_RATE),
    previous_close=_POSITIVE_PRICE,
)
def test_metrics_split_invariance(
    stmt: dict[str, float | None],
    factor: float,
    treasury_yield: float | None,
    previous_close: float,
) -> None:
    split_stmt = dict(stmt)
    if split_stmt["shares"] is not None:
        split_stmt["shares"] = split_stmt["shares"] * factor
    dps = split_stmt.get("dividends_per_share")
    if dps is not None:
        split_stmt["dividends_per_share"] = dps / factor

    before = compute_year(stmt, treasury_yield, previous_close)
    after = compute_year(split_stmt, treasury_yield, previous_close / factor)

    for label in CLOSE_YIELD_LABELS:
        _assert_close_or_both_none(after[label], before[label])

    for label in PER_SHARE_LABELS:
        before_val = before[label]
        expected = None if before_val is None else before_val / factor
        _assert_close_or_both_none(after[label], expected)


@settings(deadline=None, max_examples=100)
@given(
    label=st.sampled_from(LOCKED_LABELS),
    zero_or_none=st.sampled_from([0.0, None]),
    numerator=_FINITE_AMOUNT,
)
def test_zero_or_none_denominators_never_raise_and_format_dash(
    label: str,
    zero_or_none: float | None,
    numerator: float,
) -> None:
    stmt: dict[str, float | None] = {
        field: numerator for field in DOLLAR_FIELDS
    }
    stmt.update(
        {
            "revenue": zero_or_none,
            "equity": zero_or_none,
            "assets": zero_or_none,
            "total_liabilities": zero_or_none,
            "debt": zero_or_none,
            "net_income": zero_or_none,
            "owner_earnings": zero_or_none,
            "shares": zero_or_none,
        }
    )
    computed = compute_year(stmt, treasury_yield=zero_or_none, previous_close=zero_or_none)
    non_ratio_fields = {"Shares Outstanding", "30 Year Treasury (DGS30)"}
    for metric_label, val in computed.items():
        if metric_label in non_ratio_fields:
            assert val == zero_or_none
        else:
            assert val is None
    assert format_cell(label, None) == "—"


@settings(deadline=None, max_examples=100)
@given(
    p1=_POSITIVE_PRICE,
    p2=_POSITIVE_PRICE,
    oe1=_POSITIVE_PRICE,
    oe2=_POSITIVE_PRICE,
    non_pos_oe=st.floats(min_value=-1e6, max_value=0.0, allow_nan=False, allow_infinity=False),
)
def test_payback_years_nulls_and_monotonicity(
    p1: float,
    p2: float,
    oe1: float,
    oe2: float,
    non_pos_oe: float,
) -> None:
    assert payback_years(None, oe1) is None
    assert payback_years(p1, None) is None
    assert payback_years(p1, non_pos_oe) is None

    lo_p, hi_p = (p1, p2) if p1 <= p2 else (p2, p1)
    lo_oe, hi_oe = (oe1, oe2) if oe1 <= oe2 else (oe2, oe1)

    res_lo_p = payback_years(lo_p, hi_oe)
    res_hi_p = payback_years(hi_p, hi_oe)
    assert res_lo_p is not None and res_hi_p is not None
    assert res_lo_p <= res_hi_p

    res_lo_oe = payback_years(hi_p, lo_oe)
    res_hi_oe = payback_years(hi_p, hi_oe)
    assert res_lo_oe is not None and res_hi_oe is not None
    assert res_lo_oe >= res_hi_oe


@settings(deadline=None, max_examples=100)
@given(
    r1=_POSITIVE_RATE,
    r2=_POSITIVE_RATE,
    non_pos_r=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False, allow_infinity=False),
)
def test_treasury_payback_years_nulls_and_monotonicity(
    r1: float,
    r2: float,
    non_pos_r: float,
) -> None:
    assert treasury_payback_years(None) is None
    assert treasury_payback_years(non_pos_r) is None
    lo_r, hi_r = (r1, r2) if r1 <= r2 else (r2, r1)
    y_lo = treasury_payback_years(lo_r)
    y_hi = treasury_payback_years(hi_r)
    assert y_lo is not None and y_hi is not None
    assert y_lo >= y_hi


@settings(deadline=None, max_examples=100)
@given(
    values=st.lists(st.one_of(st.none(), _FINITE_AMOUNT), min_size=0, max_size=12),
    tail=st.lists(st.one_of(st.none(), _FINITE_AMOUNT), min_size=0, max_size=5),
    window=st.integers(min_value=1, max_value=8),
)
def test_average_oe_window_and_bounds(
    values: list[float | None],
    tail: list[float | None],
    window: int,
) -> None:
    avg = average_oe(values, window=window)
    assert avg == average_oe(values[:window], window=window)
    padded_window = values[:window] + [None] * max(0, window - len(values))
    assert avg == average_oe(padded_window + tail, window=window)
    present = [v for v in values[:window] if v is not None]
    if not present:
        assert avg is None
    else:
        assert avg is not None
        lo, hi = min(present), max(present)
        assert avg >= lo or math.isclose(avg, lo, rel_tol=1e-12, abs_tol=1e-12)
        assert avg <= hi or math.isclose(avg, hi, rel_tol=1e-12, abs_tol=1e-12)


@settings(deadline=None, max_examples=100)
@given(
    latest=st.one_of(st.none(), _FINITE_AMOUNT),
    avg=st.one_of(st.none(), _FINITE_AMOUNT),
    years=st.one_of(st.none(), st.integers(min_value=0, max_value=10)),
    prefer_longer=st.booleans(),
)
def test_conservative_pair_selection_and_ties(
    latest: float | None,
    avg: float | None,
    years: int | None,
    prefer_longer: bool,
) -> None:
    value, basis = conservative_pair(
        latest,
        avg,
        years=years,
        prefer_longer=prefer_longer,
    )
    expected_avg_label = f"{years}y avg" if isinstance(years, int) and years > 0 else "avg"
    if latest is None and avg is None:
        assert (value, basis) == (None, None)
    elif avg is None:
        assert (value, basis) == (latest, "latest")
    elif latest is None or latest == avg:
        assert (value, basis) == (avg, expected_avg_label)
    else:
        expected_val = max(latest, avg) if prefer_longer else min(latest, avg)
        expected_basis = "latest" if expected_val == latest else expected_avg_label
        assert (value, basis) == (expected_val, expected_basis)


@settings(deadline=None, max_examples=100)
@given(
    price=_POSITIVE_PRICE,
    latest_oe=st.floats(min_value=-1e6, max_value=0.0, allow_nan=False, allow_infinity=False),
    older_oe=st.lists(st.one_of(st.none(), _FINITE_AMOUNT), min_size=0, max_size=5),
    treasury_rate=st.one_of(st.none(), _POSITIVE_RATE),
)
def test_build_payback_non_positive_latest_does_not_pay_back(
    price: float,
    latest_oe: float,
    older_oe: list[float | None],
    treasury_rate: float | None,
) -> None:
    series = [latest_oe, *older_oe]
    years = [str(2025 - idx) for idx in range(len(series))]
    raw = dict(zip(years, series, strict=True))
    rows = [{"metric": "Owner Earnings per Share", "values": {}, "raw": raw}]
    block = build_payback(
        price=price,
        years=years,
        rows=rows,
        treasury_rate_decimal=treasury_rate,
    )
    assert block is not None
    assert block["pays_back"] is False
    assert block["years_at_latest"] is None
    assert block["years_conservative"] is None
    assert block["conservative_basis"] is None


@settings(deadline=None, max_examples=100)
@given(
    row_basis=st.dates(min_value=date(2010, 1, 1), max_value=date(2026, 12, 31)),
    shares=_POSITIVE_SHARES,
    dps=st.one_of(st.none(), _POSITIVE_PRICE),
    non_after_days=st.lists(st.integers(min_value=-365, max_value=0), min_size=1, max_size=5),
    bad_ratio=st.sampled_from([0.0, -2.0, math.nan, math.inf, -math.inf]),
)
def test_apply_market_splits_noop_for_prior_or_invalid_splits(
    row_basis: date,
    shares: float,
    dps: float | None,
    non_after_days: list[int],
    bad_ratio: float,
) -> None:
    statements = {
        2024: {
            "shares": shares,
            "dividends_per_share": dps,
            "shares_basis_date": row_basis,
        }
    }
    original = copy.deepcopy(statements)
    prior_splits = [
        Split(row_basis + timedelta(days=offset), 2.0) for offset in non_after_days
    ]
    invalid_splits = [Split(row_basis + timedelta(days=1), bad_ratio)]
    apply_market_splits(statements, prior_splits + invalid_splits)
    assert statements == original


@settings(deadline=None, max_examples=100)
@given(
    row_basis=st.dates(min_value=date(2010, 1, 1), max_value=date(2026, 12, 31)),
    shares=_POSITIVE_SHARES,
    dps=_POSITIVE_PRICE,
    ratios=st.lists(_SPLIT_RATIO, min_size=1, max_size=4),
)
def test_apply_market_splits_scaling_and_market_cap_dps_invariant(
    row_basis: date,
    shares: float,
    dps: float,
    ratios: list[float],
) -> None:
    statements = {
        2024: {
            "shares": shares,
            "dividends_per_share": dps,
            "shares_basis_date": row_basis,
        }
    }
    splits = [
        Split(row_basis + timedelta(days=idx + 1), ratio)
        for idx, ratio in enumerate(ratios)
    ]
    total_factor = math.prod(ratios)
    apply_market_splits(statements, splits)

    new_shares = statements[2024]["shares"]
    new_dps = statements[2024]["dividends_per_share"]
    assert isinstance(new_shares, float)
    assert isinstance(new_dps, float)
    assert math.isclose(new_shares, shares * total_factor, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(new_dps, dps / total_factor, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(new_shares * new_dps, shares * dps, rel_tol=1e-9, abs_tol=1e-9)


@settings(deadline=None, max_examples=100)
@given(
    row_basis=st.dates(min_value=date(2010, 1, 1), max_value=date(2026, 12, 31)),
    shares=_POSITIVE_SHARES,
    dps=_POSITIVE_PRICE,
    ratio=_SPLIT_RATIO,
)
def test_apply_market_splits_round_trip(
    row_basis: date,
    shares: float,
    dps: float,
    ratio: float,
) -> None:
    statements = {
        2024: {
            "shares": shares,
            "dividends_per_share": dps,
            "shares_basis_date": row_basis,
        }
    }
    apply_market_splits(statements, [Split(row_basis + timedelta(days=1), ratio)])
    apply_market_splits(statements, [Split(row_basis + timedelta(days=2), 1.0 / ratio)])

    restored_shares = statements[2024]["shares"]
    restored_dps = statements[2024]["dividends_per_share"]
    assert isinstance(restored_shares, float)
    assert isinstance(restored_dps, float)
    assert math.isclose(restored_shares, shares, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(restored_dps, dps, rel_tol=1e-9, abs_tol=1e-9)


@settings(deadline=None, max_examples=100)
@given(end=st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)))
def test_fiscal_year_label_january_cutoff(end: date) -> None:
    expected = end.year - 1 if (end.month == 1 and end.day <= 7) else end.year
    assert fiscal_year_label(end) == expected
