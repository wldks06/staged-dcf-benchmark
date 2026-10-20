"""Case-level engine: forecast rules, cost of capital, bridge, traps.

The expected numbers are derived twice: literal anchors worked by hand, and a
plain re-derivation in this file that shares no code with the engine.
"""

import pytest

from conftest import synthetic_inputs
from dcfbench.engine import cost_of_capital, trap_answers, value_case
from dcfbench.errors import ValuationError
from dcfbench.forecast import effective_tax_rate
from dcfbench.policies import PRACTITIONER, TEXTBOOK, trap_policy
from dcfbench.schema import PolicyBlock


def rederive(policy_g, tax_by_year, growth, rate, shift, cash_excess, shares):
    """Section 4.2 and 4.3 written out longhand for the synthetic firm."""
    revenue, level = [], 1210.0
    for rate_g in growth:
        level *= 1 + rate_g
        revenue.append(level)
    flows = []
    for t in range(5):
        prior = 1210.0 if t == 0 else revenue[t - 1]
        ebit = 0.20 * revenue[t]
        da = 0.05 * revenue[t]
        capex = 0.06 * revenue[t]
        dnwc = 0.10 * (revenue[t] - prior)
        if t == 4:  # terminal clean-up
            capex = da * (1 + policy_g)
            dnwc = policy_g * 0.10 * revenue[t]
        flows.append(ebit * (1 - tax_by_year[t]) + da - capex - dnwc)
    pv = sum(f / (1 + rate) ** (t + 1 - shift) for t, f in enumerate(flows))
    tv = flows[-1] * (1 + policy_g) / (rate - policy_g)
    pv_tv = tv / (1 + rate) ** (5 - shift)
    ev = pv + pv_tv
    equity = ev - 400.0 - 100.0 - 0.0 - 20.0 + cash_excess
    return flows, tv, pv, pv_tv, ev, equity, equity / shares


def test_textbook_case(inputs, valuation_date):
    cp = value_case(inputs, TEXTBOOK, valuation_date)

    # Hand-worked anchors.
    assert cp.forecast.growth == pytest.approx([0.10, 0.08, 0.06, 0.04, 0.02])
    assert cp.tax_rate == 0.21
    assert cp.rf == 0.04 and cp.erp == 0.07
    assert cp.beta_levered == pytest.approx(1.0185)
    assert cp.re == pytest.approx(0.111295)
    assert cp.rd == pytest.approx(0.057)
    assert cp.weights.E == pytest.approx(3000 / 3500)
    assert cp.wacc == pytest.approx(0.101828571429)
    assert cp.fcff == pytest.approx(
        [184.888, 202.09904, 216.8869824, 228.437421696, 250.5375842112]
    )

    flows, tv, pv, pv_tv, ev, equity, price = rederive(
        0.02, [0.21] * 5, [0.10, 0.08, 0.06, 0.04, 0.02], cp.wacc, 0.0, 200.0, 104.0
    )
    assert cp.fcff == pytest.approx(flows)
    assert cp.tv == pytest.approx(tv)
    assert cp.pv_fcff == pytest.approx(pv)
    assert cp.pv_tv == pytest.approx(pv_tv)
    assert cp.ev == pytest.approx(ev)
    assert cp.cash_excess == 200.0
    assert cp.equity == pytest.approx(equity)
    assert cp.price_per_share == pytest.approx(price)
    assert cp.tv_share == pytest.approx(pv_tv / ev)
    assert cp.implied_ev_ebitda == pytest.approx(ev / (242.0 + 60.5))
    assert cp.warnings == []


def test_practitioner_case(inputs, valuation_date):
    cp = value_case(inputs, PRACTITIONER, valuation_date)

    effective = (0.20 + 0.22 + 0.25) / 3
    assert cp.tax_rate == pytest.approx(effective)
    assert cp.rf == 0.045 and cp.erp == 0.05
    # Blume applies to the relevered beta: 0.67 * 1.0185 + 0.33.
    assert cp.beta_levered == pytest.approx(1.012395)
    assert cp.re == pytest.approx(0.09561975)
    assert cp.wacc == pytest.approx(0.0883926429)
    assert cp.forecast.growth == pytest.approx([0.10, 0.08125, 0.0625, 0.04375, 0.025])
    # Terminal year goes to the statutory rate, the others stay at the effective rate.
    assert cp.forecast.tax_rate == pytest.approx([effective] * 4 + [0.21])
    assert cp.cash_excess == pytest.approx(200.0 - 0.02 * 1210.0)

    *_, ev, equity, price = rederive(
        0.025, [effective] * 4 + [0.21], [0.10, 0.08125, 0.0625, 0.04375, 0.025],
        cp.wacc, 0.5, 175.8, 104.0,
    )
    assert cp.ev == pytest.approx(ev)
    assert cp.price_per_share == pytest.approx(price)


def test_sensitivity_grid_shape_and_center(inputs, valuation_date):
    cp = value_case(inputs, TEXTBOOK, valuation_date)
    grid = cp.sensitivity.price_grid
    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    assert cp.sensitivity.wacc[2] == pytest.approx(cp.wacc)
    assert cp.sensitivity.g[2] == pytest.approx(0.02)
    assert grid[2][2] == pytest.approx(cp.price_per_share)
    # Price falls as the rate rises and rises with g.
    assert all(grid[i][2] > grid[i + 1][2] for i in range(4))
    assert all(grid[2][j] < grid[2][j + 1] for j in range(4))


def test_trap_directions(inputs, valuation_date):
    base = value_case(inputs, TEXTBOOK, valuation_date)
    traps = trap_answers(inputs, valuation_date)
    assert set(traps) == {"T1", "T2", "T3", "T5", "T6"}
    assert all(v is not None for v in traps.values())
    # T1 pairs the bill rate with a bond-based premium, so the cost of equity is too low.
    assert traps["T1"] > base.price_per_share
    # T2 overweights cheap debt.
    assert traps["T2"] > base.price_per_share
    # T3: the coupon proxy 24.2 / 400 = 6.05 percent is above the 5.7 percent market rate.
    assert traps["T3"] < base.price_per_share
    # T6 adds SBC back and divides by the smaller share count.
    assert traps["T6"] > base.price_per_share
    assert len({round(v, 6) for v in traps.values()} | {round(base.price_per_share, 6)}) == 6


def test_trap_t1_cost_of_equity(inputs, valuation_date):
    coc = cost_of_capital(inputs, trap_policy("T1"), valuation_date)
    assert coc.re == pytest.approx(0.04 + 1.0185 * 0.05)


def test_trap_t2_book_weights(inputs, valuation_date):
    coc = cost_of_capital(inputs, trap_policy("T2"), valuation_date)
    assert coc.weight_debt == pytest.approx(500 / 1300)
    # The beta is still relevered at the market ratio.
    assert coc.beta_levered == pytest.approx(1.0185)
    assert coc.wacc == pytest.approx(800 / 1300 * 0.111295 + 500 / 1300 * 0.057 * 0.79)


def test_trap_t5_fcfe_at_wacc(inputs, valuation_date):
    cp = value_case(inputs, trap_policy("T5"), valuation_date)
    base = value_case(inputs, TEXTBOOK, valuation_date)
    assert "fcfe_at_wacc" in cp.warnings
    assert cp.discount_rate == pytest.approx(base.wacc)
    # Debt 500 grows with revenue: year 1 borrows 50 and pays 5.7 percent on 500.
    assert cp.forecast.net_borrowing[0] == pytest.approx(50.0)
    assert cp.forecast.interest[0] == pytest.approx(28.5)
    assert cp.fcff[0] == pytest.approx(184.888 - 28.5 * 0.79 + 50.0)
    # FCFE is an equity value already: no debt comes off in the bridge.
    assert cp.equity == pytest.approx(cp.ev - 20.0 + 200.0)


def test_fcfe_at_cost_of_equity_is_consistent(inputs, valuation_date):
    policy = PolicyBlock(cash_flow="FCFE", discount_rate="cost_of_equity")
    cp = value_case(inputs, policy, valuation_date)
    assert cp.discount_rate == pytest.approx(cp.re)
    assert cp.warnings == []


def test_trap_t4_is_flagged_and_explodes(inputs, valuation_date):
    base = value_case(inputs, TEXTBOOK, valuation_date)
    cp = value_case(inputs, trap_policy("T4", wacc=base.wacc), valuation_date)
    assert "terminal_spread_thin" in cp.warnings
    assert cp.tv_share > 0.95


def test_growth_above_rate_raises(inputs, valuation_date):
    with pytest.raises(ValuationError):
        value_case(inputs, PolicyBlock(g=0.2), valuation_date)


def test_traps_undefined_for_the_firm(valuation_date):
    no_debt = synthetic_inputs(debt_total=0.0, sbc=None)
    traps = trap_answers(no_debt, valuation_date)
    assert traps["T3"] is None  # no borrowings, no coupon
    assert traps["T6"] is None  # no SBC series to add back
    assert traps["T1"] is not None


def test_effective_tax_is_clipped_and_skips_loss_years():
    high = synthetic_inputs(tax_expense=[90.0, 100.0, 110.0])
    assert effective_tax_rate(high) == 0.35
    low = synthetic_inputs(tax_expense=[1.0, 1.0, 1.0])
    assert effective_tax_rate(low) == 0.10
    loss_year = synthetic_inputs(pretax_income=[-50.0, 200.0, 217.8])
    assert effective_tax_rate(loss_year) == pytest.approx((0.22 + 0.25) / 2)
    all_losses = synthetic_inputs(pretax_income=[-1.0, -1.0, -1.0])
    assert effective_tax_rate(all_losses) is None


def test_growth_is_clipped(valuation_date):
    fast = synthetic_inputs(revenue=[1000.0, 1500.0, 2250.0])
    assert value_case(fast, TEXTBOOK, valuation_date).forecast.growth[0] == 0.15
    shrinking = synthetic_inputs(revenue=[1210.0, 1100.0, 1000.0])
    assert value_case(shrinking, TEXTBOOK, valuation_date).forecast.growth[0] == 0.0


def test_lease_treatment_operating(inputs, valuation_date):
    policy = PolicyBlock(lease_treatment="operating")
    coc = cost_of_capital(inputs, policy, valuation_date)
    assert coc.weight_debt == pytest.approx(400 / 3400)
    cp = value_case(inputs, policy, valuation_date)
    assert cp.equity == pytest.approx(cp.ev - 400.0 - 20.0 + 200.0)


def test_hurdle_premium(inputs, valuation_date):
    policy = PolicyBlock(rate_structure="hurdle_premium", hurdle_premium_pp=3)
    cp = value_case(inputs, policy, valuation_date)
    assert cp.discount_rate == pytest.approx(cp.wacc + 0.03)
