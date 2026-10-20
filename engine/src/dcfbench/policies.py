"""Named policies and the constants a policy refers to.

A policy fixes every judgment call, so a case has exactly one computed answer.
Trap policies are the textbook policy with one decision changed.
"""

from __future__ import annotations

from datetime import date, timedelta

from .errors import PolicyNotSupported
from .schema import PolicyBlock

# --- Named policies ----------------------------------------------------------

TEXTBOOK = PolicyBlock()

PRACTITIONER = PolicyBlock(
    tax_on_ebit="effective",
    timing="mid_year",
    rf_source="DGS10",
    erp_source="kroll_5_0",
    beta_adjustment="blume",
    g=0.025,
    cash_treatment="operating_pct",
)

# Korea. DRAFT defaults, not yet agreed. There is no Korean
# counterpart of the RWJ 7 percent premium, so both use Damodaran's implied premium
# plus his country risk premium for Korea, which are sourced and dated.
_KR = dict(market="KR", accounting_standard="K_IFRS", currency="KRW")
KR_TEXTBOOK = PolicyBlock(
    **_KR, rf_source="KTB10Y", erp_source="damodaran_implied", country_premium_rule="damodaran_crp"
)
KR_PRACTITIONER = PRACTITIONER.model_copy(
    update=dict(
        **_KR, rf_source="KTB10Y", erp_source="damodaran_implied",
        country_premium_rule="damodaran_crp", g=0.01,
    )
)

# Japan. DRAFT defaults on the Korean pattern: the 10-year JGB, Damodaran's implied
# premium plus his country risk premium for Japan. The accounting standard is set per
# company (Japan GAAP or IFRS) by jp_policies, since EDINET filers use either.
_JP = dict(market="JP", accounting_standard="J_GAAP", currency="JPY")
JP_TEXTBOOK = PolicyBlock(
    **_JP, rf_source="JGB10Y", erp_source="damodaran_implied", country_premium_rule="damodaran_crp"
)
JP_PRACTITIONER = PRACTITIONER.model_copy(
    update=dict(
        **_JP, rf_source="JGB10Y", erp_source="damodaran_implied",
        country_premium_rule="damodaran_crp", g=0.01,
    )
)


def jp_policies(accounting_standard: str) -> dict[str, PolicyBlock]:
    """The Japanese policies for one filer's standard (J_GAAP or IFRS), with T2."""
    textbook = JP_TEXTBOOK.model_copy(update={"accounting_standard": accounting_standard})
    practitioner = JP_PRACTITIONER.model_copy(update={"accounting_standard": accounting_standard})
    return {"textbook": textbook, "practitioner": practitioner, "T2": trap_policy("T2", textbook)}


POLICIES: dict[str, PolicyBlock] = {
    "textbook": TEXTBOOK,
    "practitioner": PRACTITIONER,
    "kr_textbook": KR_TEXTBOOK,
    "kr_practitioner": KR_PRACTITIONER,
    "jp_textbook": JP_TEXTBOOK,
    "jp_practitioner": JP_PRACTITIONER,
}

# Traps that are a fixed edit of the base policy. T4 needs the case's WACC and T7
# is a property of the snapshot, so neither is listed here.
_TRAP_EDITS: dict[str, dict] = {
    "T1": {"rf_source": "DTB3", "erp_source": "kroll_5_0"},  # rf_mismatch
    "T2": {"weights": "book"},  # book_weights
    "T3": {"rd_method": "coupon"},  # coupon_cost_of_debt
    "T5": {"cash_flow": "FCFE"},  # fcfe_at_wacc
    "T6": {"sbc_treatment": "add_back", "share_count": "basic"},  # sbc_addback_no_dilution
}
TRAP_NAMES = {
    "T1": "rf_mismatch",
    "T2": "book_weights",
    "T3": "coupon_cost_of_debt",
    "T4": "g_ge_wacc_check",
    "T5": "fcfe_at_wacc",
    "T6": "sbc_addback_no_dilution",
    "T7": "lookahead",
}
T4_SPREAD = 0.0025  # g is set to WACC minus 25 basis points


def _edit(base: PolicyBlock, update: dict) -> PolicyBlock:
    # model_copy skips validation, so rebuild through the constructor.
    return PolicyBlock(**{**base.model_dump(), **update})


def trap_policy(trap: str, base: PolicyBlock = TEXTBOOK, *, wacc: float | None = None) -> PolicyBlock:
    """The base policy with one trap applied. T4 needs the base policy's WACC."""
    if trap == "T4":
        if wacc is None:
            raise ValueError("T4 sets g relative to WACC, pass wacc")
        return _edit(base, {"g": wacc - T4_SPREAD})
    if trap not in _TRAP_EDITS:
        raise KeyError(f"no policy edit for trap {trap}")
    return _edit(base, _TRAP_EDITS[trap])


# --- Constants a policy refers to ---------------------------------------------

# Equity risk premiums that are fixed numbers. The date-dependent sources
# (damodaran_implied, historical_tbond) come from the snapshot via Inputs.erp.
ERP_CONSTANTS: dict[str, float] = {
    "rwj_7": 0.070,  # RWJ, large stocks over T-bills
    "kroll_5_0": 0.050,  # Kroll recommended US ERP, over a normalized 20-year Treasury
    "fernandez_us": 0.055,  # Fernandez survey 2025, US average
}

# The instrument each source is measured against. Mixing classes is trap T1.
RF_CLASS: dict[str, str] = {
    "DTB3": "bill", "CD91": "bill", "JGB1Y": "bill",
    "DGS10": "bond", "DGS20": "bond", "normalized": "bond", "KTB3Y": "bond", "KTB10Y": "bond",
    "JGB10Y": "bond", "JGB20Y": "bond",
}
ERP_CLASS: dict[str, str] = {
    "rwj_7": "bill",
    "kroll_5_0": "bond", "fernandez_us": "bond", "damodaran_implied": "bond",
    "historical_tbond": "bond",
}

RF_MARKET: dict[str, str] = {
    "DTB3": "US", "DGS10": "US", "DGS20": "US", "normalized": "US",
    "CD91": "KR", "KTB3Y": "KR", "KTB10Y": "KR",
    "JGB1Y": "JP", "JGB10Y": "JP", "JGB20Y": "JP",
}
# Base rate for the cost of debt (rd_method rf_plus_spread): the 10-year government yield.
LONG_RF_SERIES: dict[str, str] = {"US": "DGS10", "KR": "KTB10Y", "JP": "JGB10Y"}

BLUME_WEIGHT = 0.67  # beta_adjusted = 0.67 * raw + 0.33

EFFECTIVE_TAX_CLIP = (0.10, 0.35)
GROWTH_CLIP = (0.0, 0.15)

# Statutory corporate tax rate by market: (first calendar year it applies to, rate).
# US is federal only. KR is the top national bracket plus the 10 percent local income tax.
_STATUTORY_TAX: dict[str, list[tuple[int, float]]] = {
    "US": [(1993, 0.35), (2018, 0.21)],
    "KR": [(2012, 0.242), (2018, 0.275), (2023, 0.264), (2026, 0.275)],
    # JP is the effective statutory rate for a large company in Tokyo: national corporate tax,
    # local corporate tax, inhabitant tax and the enterprise tax that is deductible.
    "JP": [(2015, 0.3211), (2016, 0.2997), (2018, 0.3062)],
}


def statutory_tax_rate(market: str, valuation_date: date) -> float:
    """Statutory rate for the first forecast year, the year starting after the valuation date."""
    if market not in _STATUTORY_TAX:
        raise PolicyNotSupported(f"no statutory tax table for market {market}")
    year = (valuation_date + timedelta(days=1)).year
    applicable = [rate for first_year, rate in _STATUTORY_TAX[market] if first_year <= year]
    if not applicable:
        raise ValueError(f"no statutory tax rate for {market} in {year}")
    return applicable[-1]


def policy_warnings(policy: PolicyBlock) -> list[str]:
    """Internal inconsistencies in a policy. The trap policies each raise one of these."""
    out: list[str] = []
    if RF_CLASS[policy.rf_source] != ERP_CLASS[policy.erp_source]:
        out.append("rf_erp_mismatch")
    if RF_MARKET[policy.rf_source] != policy.market:
        out.append("rf_market_mismatch")
    if policy.cash_flow == "FCFE" and policy.discount_rate == "wacc":
        out.append("fcfe_at_wacc")
    if policy.cash_flow == "FCFF" and policy.discount_rate == "cost_of_equity":
        out.append("fcff_at_cost_of_equity")
    if policy.sbc_treatment == "add_back" and policy.share_count == "basic":
        out.append("sbc_addback_no_dilution")
    if policy.weights == "book":
        out.append("book_weights")
    if policy.rd_method in ("coupon", "interest_over_liabilities"):
        out.append("historical_cost_of_debt")
    return out
