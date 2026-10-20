"""Deterministic forecast rules.

Every rule is mechanical so that inputs plus policy give exactly one forecast:
- Revenue growth in year 1 is the historical CAGR over the input window, clipped to
  [0, 15 percent], and fades linearly to the terminal growth g in the last year.
- EBIT, D&A, capex, NWC and SBC are held at their average share of revenue. Each
  average is the plain mean of the annual ratios.
- Change in NWC is the NWC share times the change in revenue, so the base-year
  level is the normalized one and year 1 carries no catch-up.
- With terminal clean-up on, the last year is a steady-state year: capex equals
  D&A times (1 + g), change in NWC equals g times NWC, tax is the statutory rate.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import PolicyNotSupported, ValuationError
from .policies import EFFECTIVE_TAX_CLIP, GROWTH_CLIP
from .schema import Inputs, PolicyBlock


@dataclass(frozen=True)
class Forecast:
    growth: list[float]
    revenue: list[float]
    ebit: list[float]
    tax_rate: list[float]
    da: list[float]
    capex: list[float]
    nwc: list[float]
    dnwc: list[float]
    sbc_addback: list[float]
    fcff: list[float]


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def mean_ratio(numerators: list[float], denominators: list[float]) -> float:
    return sum(n / d for n, d in zip(numerators, denominators)) / len(numerators)


def historical_cagr(revenue: list[float]) -> float:
    """Compound growth from the first to the last year of the window.

    Three fiscal years span two growth periods, so the exponent is 1 / (n - 1).
    """
    if any(r <= 0 for r in revenue):
        raise ValuationError("revenue must be positive in every year of the window")
    return (revenue[-1] / revenue[0]) ** (1 / (len(revenue) - 1)) - 1


def growth_path(g1: float, g: float, horizon: int) -> list[float]:
    """Linear fade from g1 in year 1 to g in the last year."""
    return [g1 + (g - g1) * t / (horizon - 1) for t in range(horizon)]


def effective_tax_rate(inputs: Inputs) -> float | None:
    """Mean of the annual effective rates, clipped. Years with no pretax profit are skipped.

    Returns None when no year qualifies, and the caller decides what to do.
    """
    rates = [t / p for t, p in zip(inputs.tax_expense, inputs.pretax_income) if p > 0]
    if not rates:
        return None
    return clip(sum(rates) / len(rates), *EFFECTIVE_TAX_CLIP)


def fcff(ebit: float, tax_rate: float, da: float, capex: float, dnwc: float,
         sbc_addback: float = 0.0) -> float:
    """Free cash flow to the firm. RWJ call this CFA*."""
    return ebit * (1 - tax_rate) + da - capex - dnwc + sbc_addback


def build_forecast(inputs: Inputs, policy: PolicyBlock, *, tax_rate: float,
                   statutory_rate: float) -> Forecast:
    if policy.growth_source != "history_cagr":
        raise PolicyNotSupported(f"growth_source {policy.growth_source}")
    if policy.reinvestment_rule != "tied":
        raise PolicyNotSupported(f"reinvestment_rule {policy.reinvestment_rule}")
    if policy.nwc_definition != "balance_sheet":
        raise PolicyNotSupported(f"nwc_definition {policy.nwc_definition}")
    if policy.sbc_treatment == "add_back" and inputs.sbc is None:
        raise ValuationError("sbc_treatment add_back needs Inputs.sbc")

    n = policy.horizon
    g = policy.g
    rev_hist = inputs.revenue

    g1 = clip(historical_cagr(rev_hist), *GROWTH_CLIP)
    growth = growth_path(g1, g, n)

    revenue: list[float] = []
    level = rev_hist[-1]
    for rate in growth:
        level *= 1 + rate
        revenue.append(level)

    margin = mean_ratio(inputs.ebit, rev_hist)
    da_pct = mean_ratio(inputs.da, rev_hist)
    capex_pct = mean_ratio(inputs.capex, rev_hist)
    nwc_pct = mean_ratio(inputs.nwc, rev_hist)
    sbc_pct = mean_ratio(inputs.sbc, rev_hist) if policy.sbc_treatment == "add_back" else 0.0

    ebit = [margin * r for r in revenue]
    da = [da_pct * r for r in revenue]
    capex = [capex_pct * r for r in revenue]
    nwc = [nwc_pct * r for r in revenue]
    prior = [rev_hist[-1]] + revenue[:-1]
    dnwc = [nwc_pct * (r - p) for r, p in zip(revenue, prior)]
    sbc = [sbc_pct * r for r in revenue]
    tax = [tax_rate] * n

    if policy.terminal_cleanup == "on":
        capex[-1] = da[-1] * (1 + g)
        dnwc[-1] = g * nwc[-1]
        tax[-1] = statutory_rate

    flows = [fcff(ebit[t], tax[t], da[t], capex[t], dnwc[t], sbc[t]) for t in range(n)]
    return Forecast(growth, revenue, ebit, tax, da, capex, nwc, dnwc, sbc, flows)
