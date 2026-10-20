"""Case generation. Unit tests, plus checks against the real snapshot when it is present."""

from datetime import date

import pytest

from dcfbench import generate
from dcfbench.config import SNAPSHOT_DIR
from dcfbench.data.prices import PriceHistory, is_share_split
from dcfbench.data.snapshot import Snapshot

SNAPSHOT_ID = "snap-2026-10-01-a"
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT_DIR / SNAPSHOT_ID / "manifest.json").exists(),
    reason=f"snapshot {SNAPSHOT_ID} is not on this machine",
)


@pytest.mark.parametrize("basic, diluted, expected", [
    (714e6, 722e6, (714e6, 722e6, None)),
    (714e6, 721.9, (714e6, 721.9e6, "shares_diluted scaled by 1e+06")),  # tagged in millions
    (714e6, 722e3, (714e6, 722e6, "shares_diluted scaled by 1000")),
    (714.0, 722e6, (714e6, 722e6, "shares_basic scaled by 1e+06")),
    (714e6, 30e6, (714e6, 30e6, "inconsistent")),
    (0.0, 722e6, (0.0, 722e6, "inconsistent")),  # a zero count cannot be scaled
])
def test_reconcile_share_scale(basic, diluted, expected):
    got = generate.reconcile_share_scale(basic, diluted)
    assert got[0] == pytest.approx(expected[0]) and got[1] == pytest.approx(expected[1])
    assert got[2] == expected[2]


@pytest.mark.parametrize("ratio, split", [
    (2.0, True), (20.0, True), (50.0, True), (1.5, True), (1.25, True), (0.1, True),
    (1.998, True),  # Alphabet 2014 as Yahoo lists it
    (1.324, False), (1.061, False), (1.007, False),  # spin-offs: AT&T 2022, Honeywell 2025
])
def test_split_versus_spin_off(ratio, split):
    assert is_share_split(ratio) is split


def test_spin_off_rescales_prices_but_not_shares():
    history = PriceHistory(
        "T", "USD", closes=[(date(2019, 12, 31), 29.5166), (date(2022, 12, 30), 18.41)],
        splits=[(date(2022, 4, 11), 1.324)],
    )
    # The price that traded in 2019 is recovered, the share count is left alone.
    assert history.raw_close(date(2019, 12, 31))[1] == pytest.approx(39.08, abs=0.01)
    assert history.share_split_factor(date(2019, 2, 20), date(2022, 12, 31)) == 1.0
    assert history.split_factor(date(2019, 2, 20), date(2022, 12, 31)) == 1.324


def test_select_sector_top_keeps_the_largest_per_sector():
    ranked = [("A", "Energy", 50.0), ("B", "Energy", 70.0), ("C", "Energy", 60.0), ("D", "Energy", 10.0),
              ("E", "Utilities", 5.0), ("F", "Utilities", 5.0)]
    kept = generate.select_sector_top(ranked, per_sector=2)
    assert kept == {"B": 1, "C": 2, "E": 1, "F": 2}  # ties broken by ticker, a thin sector keeps what it has
    assert generate.select_sector_top([], per_sector=2) == {}
    assert generate.select_sector_top(ranked, per_sector=10)["D"] == 4


def test_market_enterprise_value():
    from conftest import synthetic_inputs
    assert generate.market_enterprise_value(synthetic_inputs()) == 3000 + 400 + 100 + 20 - 200


# --- Against the real snapshot ----------------------------------------------------


@pytest.fixture(scope="module")
def run():
    snap = Snapshot(SNAPSHOT_ID)
    dates = [date(2019, 12, 31), date(2025, 12, 31)]
    return snap, generate.generate_us(snap, dates)


def case(result, ticker, day, label="textbook"):
    return next(c for c in result.cases if c.company.ticker == ticker
                and c.valuation_date == date.fromisoformat(day) and c.policy_label == label)


def reasons(result, ticker, day):
    return [r for e in result.exclusions
            if e.ticker == ticker and e.valuation_date == date.fromisoformat(day)
            for r in e.reasons]


@needs_snapshot
def test_johnson_and_johnson_2019_against_its_10k(run):
    """Figures from the FY2018 10-K, filed February 2019."""
    _, result = run
    inputs = case(result, "JNJ", "2019-12-31").inputs
    assert inputs.fiscal_years == ["2016", "2017", "2018"]
    assert inputs.revenue[-1] == 81_581e6
    assert inputs.da[-1] == 6_929e6
    assert inputs.capex[-1] == 3_670e6
    assert inputs.cash == 18_107e6 and inputs.st_investments == 1_580e6
    # About 27.7bn long-term plus 2.8bn loans and notes payable.
    assert inputs.debt_total == pytest.approx(30_480e6, rel=1e-3)
    assert inputs.lease_liability == 0  # before ASC 842
    assert inputs.price == pytest.approx(145.87, abs=0.01)
    assert inputs.rates["DTB3"] == pytest.approx(0.0152) and inputs.rates["DGS10"] == pytest.approx(0.0192)
    assert inputs.erp["damodaran_implied"] == pytest.approx(0.052)
    assert inputs.rating == "AAA"


@needs_snapshot
def test_every_input_has_provenance_and_nothing_looks_ahead(run):
    _, result = run
    assert len(result.cases) > 200
    for c in result.cases:
        prov = c.inputs.provenance
        for name in ("revenue", "ebit", "da", "capex", "tax_expense", "pretax_income",
                     "interest_expense", "cash", "debt_total", "shares_basic", "shares_diluted",
                     "price", "market_cap", "beta_unlevered_industry", "rating", "rates.DTB3",
                     "rates.DGS10", "rates.oas_rating"):
            assert prov.get(name), f"{c.case_id} has no provenance for {name}"
        filed = [p.filed for items in prov.values() for p in items if p.source == "edgar"]
        assert filed and max(filed) <= c.valuation_date, c.case_id


@needs_snapshot
def test_price_tool_helper_agrees_with_case_inputs(run):
    snap, result = run
    checked = 0
    for c in result.cases:
        if c.policy_label != "textbook":
            continue
        market = generate.us_market_data(snap, c.company.cik, c.company.ticker, c.valuation_date)
        assert market["close"] == pytest.approx(c.inputs.price)
        assert market["market_cap"] == pytest.approx(c.inputs.market_cap)
        checked += 1
    assert checked > 60


@needs_snapshot
def test_universe_filters(run):
    _, result = run
    assert "fye_not_december" in reasons(result, "AAPL", "2019-12-31")
    assert "financial_sic" in reasons(result, "JPM", "2019-12-31")
    assert "financial_industry" in reasons(result, "MA", "2019-12-31")
    assert "captive_finance" in reasons(result, "GM", "2025-12-31")
    assert "no_current_listing" in reasons(result, "AGN", "2019-12-31")
    # Exxon's history sits under its pre-2026 registrant.
    assert case(result, "XOM", "2019-12-31").company.cik == "0000034088"
    # Of Alphabet's two share classes the one Damodaran lists is kept.
    tickers = {c.company.ticker for c in result.cases}
    assert "GOOGL" in tickers and "GOOG" not in tickers
    firms = {d: len({c.company.ticker for c in result.cases if c.valuation_date == d})
             for d in (date(2019, 12, 31), date(2025, 12, 31))}
    assert all(30 <= n <= 50 for n in firms.values()), firms  # target range per date


@needs_snapshot
def test_share_counts_are_rebased_and_rescaled(run):
    _, result = run
    notes = {(t, d, k): v for t, d, k, v in result.notes}
    day = date(2025, 12, 31)
    # ServiceNow split 5 for 1 in December 2025, after its FY2024 10-K.
    assert notes[("NOW", day, "shares_basic_split_factor")] == "5.0"
    # McDonald's tags its diluted count in millions.
    assert notes[("MCD", day, "share_scale")] == "shares_diluted scaled by 1e+06"
    mcd = case(result, "MCD", "2025-12-31").inputs
    assert 0.9 < mcd.shares_diluted / mcd.shares_basic < 1.1
    # Honeywell's 2025 spin-off must not inflate its share count.
    assert ("HON", day, "shares_basic_split_factor") not in notes


@needs_snapshot
def test_cases_pass_the_engine_and_the_filters(run):
    _, result = run
    for c in result.cases:
        cp = c.checkpoints
        assert cp.wacc > 0 and cp.tv > 0 and len(cp.fcff) == 5
        if c.policy_label == "textbook":
            assert cp.equity > 0 and cp.price_per_share > 0
            assert all(v > 0 for v in c.inputs.ebit)
            assert set(c.trap_answers) == {"T1", "T2", "T3", "T5", "T6"}
