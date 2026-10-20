"""Pydantic models for cases.

Conventions:
- All rates are decimals (0.085 means 8.5 percent). The one exception is
  PolicyBlock.hurdle_premium_pp, which is in percentage points as its name says.
- Money values are in the reporting currency, in single units (not thousands).
- Historical arrays are ordered oldest to newest and align with Inputs.fiscal_years.
- Capex is stored as a positive outflow.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Market = Literal["US", "HK", "KR", "CN", "JP", "UK", "EU"]
AccountingStandard = Literal["US_GAAP", "IFRS", "CAS", "K_IFRS", "J_GAAP"]


class _Strict(BaseModel):
    # A typo in a field name must fail loudly, not create a silent default.
    model_config = ConfigDict(extra="forbid")


class PolicyBlock(_Strict):
    """Every judgment call of a valuation. Defaults are the textbook (RWJ) policy."""

    cash_flow: Literal["FCFF", "FCFE"] = "FCFF"
    # Rate the cash flows are discounted at.
    # Added so that trap T5 (FCFE at WACC) is an explicit one-field mismatch.
    discount_rate: Literal["wacc", "cost_of_equity"] = "wacc"
    tax_on_ebit: Literal["statutory", "effective"] = "statutory"
    sbc_treatment: Literal["expense", "add_back"] = "expense"
    lease_treatment: Literal["capitalize", "operating"] = "capitalize"
    nwc_definition: Literal["balance_sheet", "cash_flow_statement"] = "balance_sheet"
    timing: Literal["year_end", "mid_year"] = "year_end"
    horizon: Literal[5, 10] = 5
    growth_source: Literal["history_cagr", "guidance", "gdp_anchor"] = "history_cagr"
    reinvestment_rule: Literal["tied", "independent"] = "tied"
    rf_source: Literal[
        "DTB3", "DGS10", "DGS20", "normalized",  # US
        "CD91", "KTB3Y", "KTB10Y",  # KR
        "JGB1Y", "JGB10Y", "JGB20Y",  # JP
    ] = "DTB3"
    erp_source: Literal[
        "rwj_7", "kroll_5_0", "fernandez_us", "damodaran_implied", "historical_tbond"
    ] = "rwj_7"
    beta_source: Literal["damodaran_industry", "regression_5y_monthly", "published"] = (
        "damodaran_industry"
    )
    beta_adjustment: Literal["raw", "blume"] = "raw"
    relever: Literal["hamada", "harris_pringle"] = "hamada"
    rd_method: Literal["rf_plus_spread", "ytm", "coupon", "interest_over_liabilities"] = (
        "rf_plus_spread"
    )
    tax_shield_rate: Literal["statutory", "effective", "zero_if_nol"] = "statutory"
    weights: Literal["market", "book", "target"] = "market"
    target_debt_weight: float | None = Field(default=None, ge=0, le=1)
    rate_structure: Literal["firm_wide", "project", "hurdle_premium"] = "firm_wide"
    hurdle_premium_pp: float = Field(default=0.0, ge=0, le=6)
    tv_method: Literal["gordon", "exit_multiple", "value_driver"] = "gordon"
    exit_multiple: float | None = Field(default=None, gt=0)
    g: float = Field(default=0.02, ge=-0.05, le=0.5)
    terminal_cleanup: Literal["on", "off"] = "on"
    cash_treatment: Literal["all_excess", "operating_pct"] = "all_excess"
    operating_cash_pct: float = Field(default=0.02, ge=0, le=1)
    share_count: Literal["basic", "diluted"] = "diluted"
    as_of_rule: Literal["filed_on_or_before_date"] = "filed_on_or_before_date"
    market: Market = "US"
    accounting_standard: AccountingStandard = "US_GAAP"
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country_premium_rule: Literal["none", "damodaran_crp"] = "none"


class Company(_Strict):
    ticker: str
    name: str
    market: Market = "US"
    cik: str | None = None  # SEC, zero-padded to 10 digits
    corp_code: str | None = None  # DART, 8 digits
    industry_damodaran: str | None = None
    gics_sector: str | None = None  # GICS names as in force on October 4, 2026 (no history)
    gics_sub_industry: str | None = None
    fye_month: int = Field(ge=1, le=12)


class Provenance(_Strict):
    """Where one number came from. A summed input carries one item per component."""

    source: Literal["edgar", "dart", "edinet", "fred", "ecos", "yfinance", "damodaran", "derived"]
    tag: str | None = None  # XBRL tag, DART account_id, or series id
    value: float | None = None
    accn: str | None = None  # SEC accession number or DART rcept_no
    filed: date | None = None
    form: str | None = None
    period_end: date | None = None
    fiscal_year: str | None = None
    note: str | None = None  # fallback used, sign of a component, assumed zero, ...


class Inputs(_Strict):
    fiscal_years: list[str]
    revenue: list[float]
    ebit: list[float]
    da: list[float]
    capex: list[float]
    nwc: list[float]
    tax_expense: list[float]
    pretax_income: list[float]
    interest_expense: list[float]
    sbc: list[float] | None = None
    # Components of nwc, kept so the retrieval tier can be graded per input.
    receivables: list[float] | None = None
    inventory: list[float] | None = None
    payables: list[float] | None = None

    cash: float
    st_investments: float = 0.0
    debt_total: float
    lease_liability: float = 0.0
    preferred: float = 0.0
    minority_interest: float = 0.0
    book_equity: float | None = None  # needed for weights == "book" (trap T2)
    total_liabilities: float | None = None  # needed for rd_method == "interest_over_liabilities"
    shares_basic: float
    shares_diluted: float

    price: float
    market_cap: float

    # Keys are series names: DTB3, DGS10, DGS20, T10YIE, oas_rating, ytm, normalized, KTB10Y, ...
    rates: dict[str, float]
    # Date-dependent equity risk premiums (damodaran_implied, historical_tbond) and crp.
    erp: dict[str, float] = Field(default_factory=dict)
    beta_unlevered_industry: float
    rating: str

    provenance: dict[str, list[Provenance]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _aligned(self) -> "Inputs":
        n = len(self.fiscal_years)
        if n < 2:
            raise ValueError("need at least two fiscal years of history")
        for name in (
            "revenue", "ebit", "da", "capex", "nwc", "tax_expense", "pretax_income",
            "interest_expense", "sbc", "receivables", "inventory", "payables",
        ):
            arr = getattr(self, name)
            if arr is not None and len(arr) != n:
                raise ValueError(f"{name} has {len(arr)} values, fiscal_years has {n}")
        if self.shares_basic <= 0 or self.shares_diluted <= 0:
            raise ValueError("share counts must be positive")
        return self


class Weights(_Strict):
    E: float
    D: float


class Sensitivity(_Strict):
    wacc: list[float]
    g: list[float]
    # price_grid[i][j] is the price at wacc[i] and g[j]. None where g >= wacc.
    price_grid: list[list[float | None]]


class ForecastDetail(_Strict):
    """Per-year forecast lines. Reported so a wrong FCFF can be traced to its line."""

    growth: list[float]
    revenue: list[float]
    ebit: list[float]
    tax_rate: list[float]
    da: list[float]
    capex: list[float]
    nwc: list[float]
    dnwc: list[float]
    sbc_addback: list[float]
    # Only for cash_flow == FCFE.
    interest: list[float] | None = None
    net_borrowing: list[float] | None = None


class Checkpoints(_Strict):
    tax_rate: float
    rf: float
    erp: float
    beta_levered: float
    re: float
    rd: float
    weights: Weights
    wacc: float
    discount_rate: float  # the rate actually applied: wacc or re, plus any hurdle premium
    fcff: list[float]  # the discounted flows. FCFE when policy.cash_flow == "FCFE"
    tv: float
    pv_fcff: float
    pv_tv: float
    ev: float
    cash_excess: float
    equity: float
    price_per_share: float
    # Reported, not graded.
    tv_share: float
    implied_ev_ebitda: float | None = None  # ev over last historical EBITDA
    implied_exit_multiple: float | None = None  # tv over terminal-year EBITDA
    sensitivity: Sensitivity
    forecast: ForecastDetail | None = None
    warnings: list[str] = Field(default_factory=list)


class PractitionerLabel(_Strict):
    source: str  # DEFM14A, IAS36 note, appraisal report, ...
    accn: str | None = None
    banker: str | None = None
    wacc_range: tuple[float, float] | None = None
    g_range: tuple[float, float] | None = None
    multiple_range: tuple[float, float] | None = None
    price_range: tuple[float, float] | None = None


class TierVariants(_Strict):
    closed_form: bool = True
    retrieval: bool = True
    judgment: bool = False


class Case(_Strict):
    case_id: str
    version: str = "v0"
    company: Company
    valuation_date: date
    market: Market = "US"
    accounting_standard: AccountingStandard = "US_GAAP"
    currency: str = "USD"
    policy: PolicyBlock
    policy_label: str
    snapshot_id: str
    inputs: Inputs | None = None  # hidden in retrieval cases
    checkpoints: Checkpoints
    trap_answers: dict[str, float | None] = Field(default_factory=dict)
    practitioner_label: PractitionerLabel | None = None
    tier_variants: TierVariants = Field(default_factory=TierVariants)


def make_case_id(market: str, ticker: str, valuation_date: date, policy_label: str) -> str:
    return f"{market}-{ticker}-{valuation_date.isoformat()}-{policy_label}"


# --- What an agent returns ----------------------------------------------------------
# The contract between the harness (which parses model output into it) and the grader.
# Lenient on purpose: a missing field is graded as missing, not rejected by the parser.


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


class AgentCheckpoints(_Lenient):
    tax_rate: float | None = None
    rf: float | None = None
    erp: float | None = None
    beta_levered: float | None = None
    re: float | None = None
    rd: float | None = None
    weights: dict[str, float | None] | None = None  # {"E": ..., "D": ...}
    wacc: float | None = None
    discount_rate: float | None = None
    fcff: list[float | None] | None = None
    tv: float | None = None
    pv_fcff: float | None = None
    pv_tv: float | None = None
    ev: float | None = None
    cash_excess: float | None = None
    equity: float | None = None
    price_per_share: float | None = None
    tv_share: float | None = None
    implied_ev_ebitda: float | None = None
    implied_exit_multiple: float | None = None
    sensitivity: dict[str, Any] | None = None  # {"wacc": [...], "g": [...], "price_grid": [[...]]}

    @model_validator(mode="before")
    @classmethod
    def _junk_becomes_missing(cls, data: Any) -> Any:
        """A value that is not a number is graded as missing instead of rejecting the answer."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for name, value in data.items():
            if name == "weights":
                out[name] = ({str(k): _number_or_none(v) for k, v in value.items()}
                             if isinstance(value, dict) else None)
            elif name == "fcff":
                out[name] = ([_number_or_none(v) for v in value]
                             if isinstance(value, (list, tuple)) else None)
            elif name == "sensitivity":
                out[name] = value if isinstance(value, dict) else None
            elif name in cls.model_fields:
                out[name] = _number_or_none(value)
        return out


class AgentOutput(_Lenient):
    checkpoints: AgentCheckpoints = Field(default_factory=AgentCheckpoints)
    # Policy fields as the agent applied them (PolicyBlock field names). May be partial.
    policy_used: dict[str, Any] = Field(default_factory=dict)
    # Retrieval and judgment tiers: the input values the agent pulled, keyed like Inputs.
    inputs: dict[str, Any] = Field(default_factory=dict)
    # Input name -> {"tag", "accn", "filed"} or a list of those.
    provenance: dict[str, Any] = Field(default_factory=dict)
    # Problems the agent raised itself, for example "g_ge_wacc".
    flags: list[str] = Field(default_factory=list)
    notes: str | None = None
