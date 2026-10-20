"""Ground truth from inputs plus policy.

Two layers:
- Pure discounting functions (dcf, gordon_tv, equity_bridge, sensitivity_grid). The
  unit tests in Section 4.4 exercise these directly.
- value_case, which turns Inputs and a PolicyBlock into Checkpoints through the
  forecast rules and the cost of capital.

Nothing here does I/O. Every number comes in through Inputs or the policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Sequence

from .errors import PolicyNotSupported, ValuationError
from .forecast import Forecast, build_forecast, effective_tax_rate
from .policies import (
    BLUME_WEIGHT, ERP_CONSTANTS, LONG_RF_SERIES, TEXTBOOK, policy_warnings,
    statutory_tax_rate, trap_policy,
)
from .schema import Checkpoints, ForecastDetail, Inputs, PolicyBlock, Sensitivity, Weights

SENSITIVITY_RATE_STEPS = (-0.02, -0.01, 0.0, 0.01, 0.02)
SENSITIVITY_G_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)
THIN_SPREAD = 0.005  # discount rate minus g below this is flagged


# --- Pure discounting ----------------------------------------------------------


@dataclass(frozen=True)
class DCFResult:
    pv_by_year: list[float]
    pv_flows: float
    tv: float
    pv_tv: float
    ev: float
    tv_share: float


def gordon_tv(last_flow: float, rate: float, g: float) -> float:
    """Terminal value at the end of the last year: flow * (1 + g) / (rate - g)."""
    if g >= rate:
        raise ValuationError(f"terminal growth {g:.4f} is not below the discount rate {rate:.4f}")
    return last_flow * (1 + g) / (rate - g)


def dcf(flows: Sequence[float], rate: float, *, g: float | None = None,
        tv: float | None = None, shift: float = 0.0) -> DCFResult:
    """Present value of the flows plus a terminal value.

    Pass g for a Gordon terminal value or tv for a given one (exit multiple).
    shift is 0 for year-end flows and 0.5 for mid-year flows. A Gordon terminal
    value capitalizes flows that carry the same timing, so it is discounted over
    n - shift years. A given terminal value is a value at the end of year n and is
    discounted over n years.
    """
    if (g is None) == (tv is None):
        raise ValueError("pass exactly one of g or tv")
    if rate <= -1:
        raise ValuationError("discount rate must be above -100 percent")
    n = len(flows)
    pv_by_year = [f / (1 + rate) ** (t - shift) for t, f in enumerate(flows, start=1)]
    if g is not None:
        tv_value = gordon_tv(flows[-1], rate, g)
        pv_tv = tv_value / (1 + rate) ** (n - shift)
    else:
        tv_value = tv
        pv_tv = tv_value / (1 + rate) ** n
    pv_flows = sum(pv_by_year)
    ev = pv_flows + pv_tv
    return DCFResult(pv_by_year, pv_flows, tv_value, pv_tv, ev, pv_tv / ev if ev else float("nan"))


def equity_bridge(ev: float, *, debt: float = 0.0, leases: float = 0.0, preferred: float = 0.0,
                  minority: float = 0.0, cash_excess: float = 0.0) -> float:
    return ev - debt - leases - preferred - minority + cash_excess


def sensitivity_grid(flows: Sequence[float], rates: Sequence[float], gs: Sequence[float], *,
                     shift: float = 0.0,
                     transform: Callable[[float], float] = lambda ev: ev) -> list[list[float | None]]:
    """transform(EV) for every rate and g, with the explicit flows held fixed.

    Rows follow rates, columns follow gs. A cell is None where g is not below the rate.
    """
    grid: list[list[float | None]] = []
    for rate in rates:
        row: list[float | None] = []
        for g in gs:
            try:
                row.append(transform(dcf(flows, rate, g=g, shift=shift).ev))
            except ValuationError:
                row.append(None)
        grid.append(row)
    return grid


# --- Cost of capital -------------------------------------------------------------


@dataclass(frozen=True)
class CostOfCapital:
    tax_shield: float
    rf: float
    erp: float
    beta_levered: float
    re: float
    rd: float
    weight_equity: float
    weight_debt: float
    wacc: float
    discount_rate: float


def _rate(inputs: Inputs, series: str) -> float:
    if series not in inputs.rates:
        raise ValuationError(f"rate series {series} is not in the inputs")
    return inputs.rates[series]


def _erp(inputs: Inputs, policy: PolicyBlock) -> float:
    source = policy.erp_source
    if source in ERP_CONSTANTS:
        erp = ERP_CONSTANTS[source]
    elif source in inputs.erp:
        erp = inputs.erp[source]
    else:
        raise ValuationError(f"erp source {source} is not in the inputs")
    if policy.country_premium_rule == "damodaran_crp":
        if "crp" not in inputs.erp:
            raise ValuationError("country_premium_rule damodaran_crp needs inputs.erp['crp']")
        erp += inputs.erp["crp"]
    return erp


def debt_claims(inputs: Inputs, policy: PolicyBlock) -> float:
    """Debt as the policy defines it: borrowings, plus lease liabilities when capitalized."""
    leases = inputs.lease_liability if policy.lease_treatment == "capitalize" else 0.0
    return inputs.debt_total + leases


def cost_of_capital(inputs: Inputs, policy: PolicyBlock, valuation_date: date) -> CostOfCapital:
    if policy.beta_source != "damodaran_industry":
        raise PolicyNotSupported(f"beta_source {policy.beta_source}")
    if policy.rate_structure == "project":
        raise PolicyNotSupported("rate_structure project")

    statutory = statutory_tax_rate(policy.market, valuation_date)
    if policy.tax_shield_rate == "statutory":
        tax_shield = statutory
    elif policy.tax_shield_rate == "effective":
        effective = effective_tax_rate(inputs)
        tax_shield = statutory if effective is None else effective
    else:  # zero_if_nol
        tax_shield = 0.0 if inputs.pretax_income[-1] <= 0 else statutory

    rf = _rate(inputs, policy.rf_source)
    erp = _erp(inputs, policy)

    debt = debt_claims(inputs, policy)
    if inputs.market_cap <= 0:
        raise ValuationError("market cap must be positive")

    if policy.weights == "market":
        equity = inputs.market_cap
    elif policy.weights == "book":
        if inputs.book_equity is None or inputs.book_equity <= 0:
            raise ValuationError("book weights need a positive Inputs.book_equity")
        equity = inputs.book_equity
    else:  # target
        if policy.target_debt_weight is None or policy.target_debt_weight >= 1:
            raise ValuationError("target weights need policy.target_debt_weight below 1")
        equity = None

    if equity is None:
        weight_debt = policy.target_debt_weight
        debt_to_equity = weight_debt / (1 - weight_debt)
    else:
        weight_debt = debt / (debt + equity)
        # The beta is relevered at the market debt to equity ratio whatever the weights are.
        debt_to_equity = debt / inputs.market_cap
    weight_equity = 1 - weight_debt

    if policy.relever == "hamada":
        beta = inputs.beta_unlevered_industry * (1 + (1 - tax_shield) * debt_to_equity)
    else:  # harris_pringle, debt beta of zero
        beta = inputs.beta_unlevered_industry * (1 + debt_to_equity)
    if policy.beta_adjustment == "blume":
        beta = BLUME_WEIGHT * beta + (1 - BLUME_WEIGHT)

    re = rf + beta * erp

    if policy.rd_method == "rf_plus_spread":
        if policy.market not in LONG_RF_SERIES:
            raise PolicyNotSupported(f"no long government yield defined for market {policy.market}")
        rd = _rate(inputs, LONG_RF_SERIES[policy.market]) + _rate(inputs, "oas_rating")
    elif policy.rd_method == "ytm":
        rd = _rate(inputs, "ytm")
    elif policy.rd_method == "coupon":
        # Version zero proxy for the average coupon: interest expense over book borrowings.
        if inputs.debt_total <= 0:
            raise ValuationError("coupon cost of debt is undefined without borrowings")
        rd = inputs.interest_expense[-1] / inputs.debt_total
    else:  # interest_over_liabilities
        if not inputs.total_liabilities or inputs.total_liabilities <= 0:
            raise ValuationError("interest_over_liabilities needs Inputs.total_liabilities")
        rd = inputs.interest_expense[-1] / inputs.total_liabilities

    wacc = weight_equity * re + weight_debt * rd * (1 - tax_shield)
    discount_rate = wacc if policy.discount_rate == "wacc" else re
    if policy.rate_structure == "hurdle_premium":
        discount_rate += policy.hurdle_premium_pp / 100

    return CostOfCapital(tax_shield, rf, erp, beta, re, rd, weight_equity, weight_debt, wacc,
                         discount_rate)


# --- Case level ------------------------------------------------------------------


def _fcfe(forecast: Forecast, inputs: Inputs, debt0: float, rd: float,
          tax_shield: float) -> tuple[list[float], list[float], list[float]]:
    """FCFE = FCFF - interest * (1 - t) + net borrowing, with debt held at its share of revenue."""
    base = inputs.revenue[-1]
    debt = [debt0 * r / base for r in forecast.revenue]
    prior = [debt0] + debt[:-1]
    interest = [rd * p for p in prior]
    net_borrowing = [d - p for d, p in zip(debt, prior)]
    flows = [f - i * (1 - tax_shield) + nb
             for f, i, nb in zip(forecast.fcff, interest, net_borrowing)]
    return flows, interest, net_borrowing


def value_case(inputs: Inputs, policy: PolicyBlock, valuation_date: date) -> Checkpoints:
    """The one computed answer for a case, with a checkpoint at every step."""
    warnings = policy_warnings(policy)

    statutory = statutory_tax_rate(policy.market, valuation_date)
    if policy.tax_on_ebit == "statutory":
        tax_rate = statutory
    else:
        effective = effective_tax_rate(inputs)
        if effective is None:
            warnings.append("effective_tax_undefined_used_statutory")
            tax_rate = statutory
        else:
            tax_rate = effective

    coc = cost_of_capital(inputs, policy, valuation_date)
    forecast = build_forecast(inputs, policy, tax_rate=tax_rate, statutory_rate=statutory)
    debt = debt_claims(inputs, policy)

    interest = net_borrowing = None
    if policy.cash_flow == "FCFF":
        flows = forecast.fcff
    else:
        flows, interest, net_borrowing = _fcfe(forecast, inputs, debt, coc.rd, coc.tax_shield)

    rate = coc.discount_rate
    shift = 0.5 if policy.timing == "mid_year" else 0.0
    terminal_ebitda = forecast.ebit[-1] + forecast.da[-1]

    fixed_tv: float | None = None
    if policy.tv_method == "gordon":
        result = dcf(flows, rate, g=policy.g, shift=shift)
    elif policy.tv_method == "exit_multiple":
        if policy.cash_flow != "FCFF" or policy.exit_multiple is None:
            raise ValuationError("exit_multiple needs FCFF flows and policy.exit_multiple")
        fixed_tv = terminal_ebitda * policy.exit_multiple
        result = dcf(flows, rate, tv=fixed_tv, shift=shift)
    else:
        raise PolicyNotSupported(f"tv_method {policy.tv_method}")

    cash_total = inputs.cash + inputs.st_investments
    if policy.cash_treatment == "all_excess":
        cash_excess = cash_total
    else:
        cash_excess = max(0.0, cash_total - policy.operating_cash_pct * inputs.revenue[-1])

    def to_equity(ev: float) -> float:
        # FCFE values the equity directly, so lenders' claims are already out of the flows.
        return equity_bridge(
            ev,
            debt=debt if policy.cash_flow == "FCFF" else 0.0,
            preferred=inputs.preferred,
            minority=inputs.minority_interest,
            cash_excess=cash_excess,
        )

    shares = inputs.shares_diluted if policy.share_count == "diluted" else inputs.shares_basic
    equity = to_equity(result.ev)
    price = equity / shares

    rates = [rate + step for step in SENSITIVITY_RATE_STEPS]
    gs = [policy.g + step for step in SENSITIVITY_G_STEPS]
    if fixed_tv is None:
        grid = sensitivity_grid(flows, rates, gs, shift=shift,
                                transform=lambda ev: to_equity(ev) / shares)
    else:
        # A multiple-based terminal value does not depend on g, so only the rate moves.
        grid = [[to_equity(dcf(flows, r, tv=fixed_tv, shift=shift).ev) / shares for _ in gs]
                for r in rates]

    if policy.tv_method == "gordon" and rate - policy.g < THIN_SPREAD:
        warnings.append("terminal_spread_thin")
    if equity <= 0:
        warnings.append("equity_not_positive")
    if any(f <= 0 for f in flows):
        warnings.append("non_positive_flow")

    last_ebitda = inputs.ebit[-1] + inputs.da[-1]
    return Checkpoints(
        tax_rate=tax_rate,
        rf=coc.rf,
        erp=coc.erp,
        beta_levered=coc.beta_levered,
        re=coc.re,
        rd=coc.rd,
        weights=Weights(E=coc.weight_equity, D=coc.weight_debt),
        wacc=coc.wacc,
        discount_rate=rate,
        fcff=list(flows),
        tv=result.tv,
        pv_fcff=result.pv_flows,
        pv_tv=result.pv_tv,
        ev=result.ev,
        cash_excess=cash_excess,
        equity=equity,
        price_per_share=price,
        tv_share=result.tv_share,
        implied_ev_ebitda=result.ev / last_ebitda if last_ebitda > 0 else None,
        implied_exit_multiple=result.tv / terminal_ebitda if terminal_ebitda > 0 else None,
        sensitivity=Sensitivity(wacc=rates, g=gs, price_grid=grid),
        forecast=ForecastDetail(
            growth=forecast.growth, revenue=forecast.revenue, ebit=forecast.ebit,
            tax_rate=forecast.tax_rate, da=forecast.da, capex=forecast.capex,
            nwc=forecast.nwc, dnwc=forecast.dnwc, sbc_addback=forecast.sbc_addback,
            interest=interest, net_borrowing=net_borrowing,
        ),
        warnings=warnings,
    )


TRAPS_WITH_ANSWERS = ("T1", "T2", "T3", "T5", "T6")


def trap_answers(inputs: Inputs, valuation_date: date,
                 base: PolicyBlock = TEXTBOOK) -> dict[str, float | None]:
    """Final price under each trap policy. None where the trap is undefined for the firm."""
    out: dict[str, float | None] = {}
    for trap in TRAPS_WITH_ANSWERS:
        try:
            out[trap] = value_case(inputs, trap_policy(trap, base), valuation_date).price_per_share
        except ValuationError:
            out[trap] = None
    return out
