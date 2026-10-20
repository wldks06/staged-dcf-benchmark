"""Universe filter, input assembly and case generation.

Reads the snapshot only. A company that fails any step is excluded with reason
codes instead of being patched with a default, and every fallback is logged.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .data import damodaran, edgar, fred, prices, universe
from .data.snapshot import Snapshot, SnapshotError
from .engine import trap_answers, value_case
from .errors import PolicyNotSupported, ValuationError
from .policies import PRACTITIONER, TEXTBOOK, statutory_tax_rate, trap_policy
from .schema import Case, Company, Inputs, PolicyBlock, Provenance, make_case_id

US_RATE_SERIES = ("DTB3", "DGS10", "DGS20", "T10YIE")
FINANCIAL_SIC = range(6000, 6800)  # banks, insurers, brokers, asset managers, REITs
MAX_STATEMENT_AGE_DAYS = 400  # latest fiscal year end must be within this of the valuation date
EV_RATIO_BAND = (0.3, 3.0)  # DCF enterprise value over market enterprise value, outside is inspected
# Damodaran industry groups whose unlevered beta is built from balance sheets full of
# financial debt (about 0.10 for payment networks). Relevering it at an operating
# company's own leverage gives a meaningless cost of equity, so these are out.
FINANCIAL_INDUSTRY_PREFIXES = (
    "Bank", "Brokerage", "Financial Svcs", "Insurance", "Investments & Asset", "R.E.I.T",
    "Reinsurance", "Retail (REITs)",
)
# Consolidated debt is mostly the finance arm's, which an FCFF valuation cannot carry.
MANUAL_EXCLUSIONS = {"GM": "captive_finance", "F": "captive_finance"}
MIN_PLAUSIBLE_MARKET_CAP = 1e9  # an index member below this means a mis-scaled share count
SHARE_SCALES = (1e3, 1e6)
# Closer than this to the Gordon singularity a few basis points of WACC move the price by
# multiples, so the case cannot be graded fairly (Boeing 2019 under book weights: 0.19 points).
MIN_TERMINAL_SPREAD = 0.01
TRAP_VISIBLE_REL = 0.02  # a trap shows when its price is further than this from the true one

JUDGMENT_SUBSET_SIZE = 50  # company-dates that also run in the judgment tier
JUDGMENT_SEED = 0

# Policies generated as full cases in version zero.
US_POLICIES: dict[str, PolicyBlock] = {
    "textbook": TEXTBOOK,
    "practitioner": PRACTITIONER,
    "T1": trap_policy("T1"),
    "T2": trap_policy("T2"),
}


@dataclass
class Candidate:
    ticker: str
    name: str
    cik: str
    sic: int | None
    gics_sector: str | None = None  # set under the sector rule


@dataclass
class Exclusion:
    market: str
    ticker: str
    valuation_date: date
    reasons: list[str]


@dataclass
class Built:
    company: Company
    inputs: Inputs
    fallbacks: list[str] = field(default_factory=list)
    notes: dict = field(default_factory=dict)


# --- United States -------------------------------------------------------------------


UNIVERSE_RULES = ("sp100", "sector")
PER_SECTOR = 5  # companies kept per GICS sector and valuation date under the sector rule


def has_annual_report(snap: Snapshot, cik: str) -> bool:
    """Whether the registrant files 10-Ks (a foreign private issuer files 20-F or 40-F,
    with IFRS tags the US pipeline does not read)."""
    recent = edgar.load_submissions(snap, cik).get("filings", {}).get("recent", {})
    return any(form in edgar.ANNUAL_FORMS for form in recent.get("form", []))


def us_sector_candidates(snap: Snapshot) -> tuple[list[Candidate], list[Exclusion]]:
    """The sector pool's companies that have SEC data and file 10-Ks, one entry per company."""
    ticker_map = edgar.load_ticker_map(snap)
    candidates: dict[str, Candidate] = {}
    excluded: list[Exclusion] = []
    for seed in universe.load_us_sector_seed():
        cik = universe.cik_for(seed.ticker, ticker_map)
        if cik is None or not snap.has(f"edgar/companyfacts/CIK{cik}.json"):
            excluded.append(Exclusion("US", seed.ticker, date.min, ["no_sec_data"]))
            continue
        if cik in candidates:
            continue
        if not has_annual_report(snap, cik):
            excluded.append(Exclusion("US", seed.ticker, date.min, ["not_a_10k_filer"]))
            continue
        sic = edgar.load_submissions(snap, cik).get("sic")
        candidates[cik] = Candidate(seed.ticker, seed.name, cik, int(sic) if sic else None, seed.gics_sector)
    return sorted(candidates.values(), key=lambda c: c.ticker), excluded


def select_sector_top(ranked: list[tuple[str, str, float]], per_sector: int = PER_SECTOR) -> dict[str, int]:
    """ticker -> rank within its sector for the per_sector largest of each sector.

    ranked holds (ticker, sector, market_cap) for every company that passed the filters.
    """
    out: dict[str, int] = {}
    by_sector: dict[str, list[tuple[str, float]]] = {}
    for ticker, sector, cap in ranked:
        by_sector.setdefault(sector, []).append((ticker, cap))
    for sector, items in by_sector.items():
        items.sort(key=lambda item: (-item[1], item[0]))
        for rank, (ticker, _) in enumerate(items[:per_sector], start=1):
            out[ticker] = rank
    return out


def us_candidates(snap: Snapshot, as_of: date,
                  industry_map: dict[str, str]) -> tuple[list[Candidate], list[Exclusion]]:
    """S&P 100 members on as_of that have SEC data, one entry per company."""
    ticker_map = edgar.load_ticker_map(snap)
    candidates: dict[str, Candidate] = {}
    excluded: list[Exclusion] = []
    members = universe.load_sp100(snap, as_of)
    # Of two share classes of one company (GOOG, GOOGL) keep the one Damodaran lists.
    members.sort(key=lambda m: universe.current_ticker(m.ticker) not in industry_map)
    for member in members:
        current = universe.current_ticker(member.ticker)
        cik = universe.cik_for(current, ticker_map)
        if cik is None or not snap.has(f"edgar/companyfacts/CIK{cik}.json"):
            excluded.append(Exclusion("US", edgar.normalize_ticker(member.ticker), as_of,
                                      ["no_current_listing"]))
            continue
        if cik in candidates:
            continue
        sic = edgar.load_submissions(snap, cik).get("sic")
        candidates[cik] = Candidate(current, member.name, cik, int(sic) if sic else None)
    return sorted(candidates.values(), key=lambda c: c.ticker), excluded


class UsContext:
    """Everything that depends on the valuation date but not on the company."""

    def __init__(self, snap: Snapshot, as_of: date, industry_map: dict[str, str]):
        self.snap = snap
        self.as_of = as_of
        self.industry_map = industry_map
        self.gics = universe.load_gics_labels()
        self.statutory = statutory_tax_rate("US", as_of)
        self.jan_year = damodaran.january_year(as_of)
        self.betas = damodaran.load_industry_betas(snap, self.jan_year)
        self.spreads, self.spread_key = damodaran.load_spreads(snap, self.jan_year)
        self.rating_table = damodaran.load_rating_table(snap)
        erp_year = damodaran.year_end(as_of)
        self.erp = {"damodaran_implied": damodaran.load_implied_erp(snap, erp_year)}
        self.rates: dict[str, float] = {}
        self.provenance: dict[str, list[Provenance]] = {
            "erp.damodaran_implied": [Provenance(
                source="damodaran", tag="histimpl.xls:Implied ERP (FCFE)",
                value=self.erp["damodaran_implied"], fiscal_year=str(erp_year))],
        }
        for series_id in US_RATE_SERIES:
            obs = fred.value_on_or_before(fred.load_series(snap, series_id), as_of)
            if obs is None:
                raise SnapshotError(f"no {series_id} observation on or before {as_of}")
            self.rates[series_id] = obs[1] / 100  # FRED quotes percent
            self.provenance[f"rates.{series_id}"] = [Provenance(
                source="fred", tag=series_id, value=obs[1] / 100, period_end=obs[0])]


def _values(series: list[edgar.Resolved]) -> list[float]:
    return [r.value for r in series]


def _provenance(series: list[edgar.Resolved]) -> list[Provenance]:
    return [item for r in series for item in r.provenance]


def build_us_inputs(ctx: UsContext, cand: Candidate) -> Built | Exclusion:
    snap, as_of = ctx.snap, ctx.as_of

    def exclude(*reasons: str) -> Exclusion:
        return Exclusion("US", cand.ticker, as_of, list(reasons))

    if cand.sic in FINANCIAL_SIC:
        return exclude("financial_sic")
    if cand.ticker in MANUAL_EXCLUSIONS:
        return exclude(MANUAL_EXCLUSIONS[cand.ticker])
    industry = ctx.industry_map.get(cand.ticker)
    if industry is not None and industry.startswith(FINANCIAL_INDUSTRY_PREFIXES):
        return exclude("financial_industry")

    ci = edgar.resolve_company(edgar.load_facts(snap, cand.cik), as_of)
    if not ci.series:
        return exclude(*ci.issues)
    latest = ci.fiscal_year_ends[-1]
    # 52-week years can end in the first days of January, hence the 15-day shift.
    if (latest - timedelta(days=15)).month != 12:
        return exclude("fye_not_december")
    if (as_of - latest).days > MAX_STATEMENT_AGE_DAYS:
        return exclude("stale_financials")
    if ci.issues:
        return exclude(*ci.issues)

    s, k = ci.series, ci.scalars
    nwc = [r.value + i.value - p.value
           for r, i, p in zip(s["receivables"], s["inventory"], s["payables"])]

    # Universe filter: positive EBIT and positive FCFF in each of the three years.
    ebit = _values(s["ebit"])
    if any(v <= 0 for v in ebit):
        return exclude("negative_ebit")
    prior = ci.prior_nwc
    notes: dict = {}
    if all(name in prior and prior[name].value is not None
           for name in ("receivables", "inventory", "payables")):
        nwc_before = prior["receivables"].value + prior["inventory"].value - prior["payables"].value
    else:
        nwc_before = nwc[0]  # no balance sheet before the window: first-year change taken as zero
        notes["first_year_dnwc"] = "not available, taken as zero in the FCFF filter"
    levels = [nwc_before] + nwc
    hist_fcff = [
        ebit[t] * (1 - ctx.statutory) + s["da"][t].value - s["capex"][t].value
        - (levels[t + 1] - levels[t])
        for t in range(len(ebit))
    ]
    if any(v <= 0 for v in hist_fcff):
        return exclude("negative_fcff")

    # Price, and share counts moved onto the share basis of the valuation date.
    symbol = cand.ticker
    if not snap.has(f"prices/{symbol}.json"):
        return exclude("no_price")
    history = prices.load_prices(snap, symbol)
    close = history.raw_close(as_of)
    if close is None:
        return exclude("no_price")
    price_date, price = close

    def rebased(resolved: edgar.Resolved, label: str) -> float:
        filed = max(p.filed for p in resolved.provenance if p.filed)
        factor = history.share_split_factor(filed, as_of)
        if factor != 1.0:
            notes[f"{label}_split_factor"] = factor
        return resolved.value * factor

    try:
        counts = rebased(k["shares_basic"], "shares_basic"), rebased(k["shares_diluted"], "shares_diluted")
    except prices.AmbiguousCorporateAction:
        return exclude("ambiguous_split_event")
    shares_basic, shares_diluted, scale_note = reconcile_share_scale(*counts)
    if scale_note == "inconsistent":
        return exclude("share_counts_inconsistent")
    if scale_note:
        notes["share_scale"] = scale_note
    market_cap = price * shares_basic
    if market_cap < MIN_PLAUSIBLE_MARKET_CAP:
        return exclude("implausible_market_cap")

    if industry is None or industry not in ctx.betas:
        return exclude("no_industry_beta")
    beta = ctx.betas[industry]

    interest = s["interest_expense"][-1].value
    coverage = ebit[-1] / interest if interest > 0 else float("inf")
    rating_label = damodaran.synthetic_rating(coverage, ctx.rating_table)
    if rating_label not in ctx.spreads:
        return exclude("no_spread_for_rating")
    spread = ctx.spreads[rating_label]

    provenance: dict[str, list[Provenance]] = {name: _provenance(s[name]) for name in s}
    provenance.update({name: list(k[name].provenance) for name in k})
    provenance.update(ctx.provenance)
    provenance["price"] = [Provenance(source="yfinance", tag=symbol, value=price,
                                      period_end=price_date,
                                      note="close as traded, later splits undone")]
    provenance["market_cap"] = [Provenance(source="derived", value=market_cap,
                                           note="price times shares_basic")]
    for label in ("shares_basic", "shares_diluted"):
        factor = notes.get(f"{label}_split_factor")
        if factor:
            provenance[label].append(Provenance(
                source="derived", note=f"multiplied by {factor:g} for stock splits after the filing"))
        if scale_note and scale_note.startswith(label):
            provenance[label].append(Provenance(
                source="derived", note=f"{scale_note}: the filing tags the count in a larger unit"))
    provenance["nwc"] = [Provenance(source="derived",
                                    note="receivables plus inventory minus payables")]
    provenance["beta_unlevered_industry"] = [Provenance(
        source="damodaran", tag=f"{beta.key}:{industry}", value=beta.unlevered,
        period_end=beta.date_updated)]
    provenance["rating"] = [Provenance(
        source="derived", value=None if coverage == float("inf") else coverage,
        note=f"synthetic rating {rating_label} from EBIT over interest expense")]
    provenance["rates.oas_rating"] = [Provenance(
        source="damodaran", tag=f"{ctx.spread_key}:{rating_label}", value=spread,
        note=f"default spread, January {ctx.jan_year} table")]

    inputs = Inputs(
        fiscal_years=[edgar.fiscal_year_label(e) for e in ci.fiscal_year_ends],
        revenue=_values(s["revenue"]), ebit=ebit, da=_values(s["da"]),
        capex=_values(s["capex"]), nwc=nwc, tax_expense=_values(s["tax_expense"]),
        pretax_income=_values(s["pretax_income"]),
        interest_expense=_values(s["interest_expense"]),
        sbc=_values(s["sbc"]) if all(r.value is not None for r in s["sbc"]) else None,
        receivables=_values(s["receivables"]), inventory=_values(s["inventory"]),
        payables=_values(s["payables"]),
        cash=k["cash"].value, st_investments=k["st_investments"].value,
        debt_total=k["debt_total"].value, lease_liability=k["lease_liability"].value,
        preferred=k["preferred"].value, minority_interest=k["minority_interest"].value,
        book_equity=k["book_equity"].value, total_liabilities=k["total_liabilities"].value,
        shares_basic=shares_basic, shares_diluted=shares_diluted,
        price=price, market_cap=market_cap,
        rates={**ctx.rates, "oas_rating": spread}, erp=dict(ctx.erp),
        beta_unlevered_industry=beta.unlevered, rating=rating_label.split("/")[-1],
        provenance=provenance,
    )
    gics = ctx.gics.get(("US", cand.ticker))
    company = Company(ticker=cand.ticker, name=cand.name, market="US", cik=cand.cik,
                      industry_damodaran=industry, fye_month=12,
                      gics_sector=gics.sector if gics else cand.gics_sector,
                      gics_sub_industry=gics.sub_industry if gics else None)
    return Built(company, inputs, list(ci.fallbacks), notes)


def reconcile_share_scale(basic: float, diluted: float) -> tuple[float, float, str | None]:
    """Bring a share count tagged in thousands or millions onto the scale of the other one.

    Basic and diluted counts are within a factor of two of each other. When they are
    not, the smaller one was tagged in a larger unit. Returns both counts and a note,
    which is "inconsistent" when no power of a thousand reconciles them, or when a
    count is not positive (a registrant that tags zero shares).
    """
    if basic <= 0 or diluted <= 0:
        return basic, diluted, "inconsistent"
    ratio = diluted / basic
    if 0.5 <= ratio <= 2:
        return basic, diluted, None
    for factor in SHARE_SCALES:
        if 0.5 <= ratio * factor <= 2:
            return basic, diluted * factor, f"shares_diluted scaled by {factor:g}"
        if 0.5 <= ratio / factor <= 2:
            return basic * factor, diluted, f"shares_basic scaled by {factor:g}"
    return basic, diluted, "inconsistent"


def us_market_data(snap: Snapshot, cik: str, symbol: str, as_of: date) -> dict | None:
    """Close as traded, shares on the valuation-date share basis, and market cap.

    The agents' price tool calls this, so it must agree with build_us_inputs.
    """
    if not snap.has(f"prices/{symbol}.json"):
        return None
    store = edgar.load_facts(snap, cik)
    ends = store.fiscal_year_ends(as_of, 1)
    history = prices.load_prices(snap, symbol)
    close = history.raw_close(as_of)
    if not ends or close is None:
        return None
    shares, _ = edgar.shares_outstanding(store, as_of, ends[0])
    diluted = edgar.diluted_shares(store, as_of, ends[0])
    if shares.value is None or diluted.value is None:
        return None
    try:
        factor = history.share_split_factor(max(p.filed for p in shares.provenance if p.filed), as_of)
        diluted_factor = history.share_split_factor(
            max(p.filed for p in diluted.provenance if p.filed), as_of)
    except prices.AmbiguousCorporateAction:
        return None
    # The same scale check as build_us_inputs, so a count tagged in millions cannot differ here.
    count, _, note = reconcile_share_scale(shares.value * factor, diluted.value * diluted_factor)
    if note == "inconsistent":
        return None
    return {
        "price_date": close[0], "close": close[1], "shares_outstanding": count,
        "split_factor": factor, "market_cap": close[1] * count, "currency": history.currency,
    }


# --- Cases ---------------------------------------------------------------------------


def market_enterprise_value(inputs: Inputs) -> float:
    return (inputs.market_cap + inputs.debt_total + inputs.lease_liability + inputs.preferred
            + inputs.minority_interest - inputs.cash - inputs.st_investments)


def make_cases(built: Built, as_of: date, snapshot_id: str,
               policies: dict[str, PolicyBlock]) -> tuple[list[Case], list[str]]:
    """One case per policy. Returns the cases and the reasons for any policy that failed."""
    cases, failures = [], []
    for label, policy in policies.items():
        try:
            checkpoints = value_case(built.inputs, policy, as_of)
            # What an agent gets if it applies this case's policy and falls into one trap.
            traps = trap_answers(built.inputs, as_of, base=policy)
        except (ValuationError, PolicyNotSupported) as exc:
            failures.append(f"policy_undefined:{label}:{exc}")
            continue
        if policy.tv_method == "gordon" and checkpoints.discount_rate - policy.g < MIN_TERMINAL_SPREAD:
            failures.append(f"policy_undefined:{label}:discount rate within one point of g")
            continue
        cases.append(Case(
            case_id=make_case_id(policy.market, built.company.ticker, as_of, label),
            company=built.company, valuation_date=as_of, market=policy.market,
            accounting_standard=policy.accounting_standard, currency=policy.currency,
            policy=policy, policy_label=label, snapshot_id=snapshot_id,
            inputs=built.inputs, checkpoints=checkpoints, trap_answers=traps,
        ))
    return cases, failures


@dataclass
class RunResult:
    cases: list[Case] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    fallbacks: list[tuple[str, date, str]] = field(default_factory=list)
    notes: list[tuple[str, date, str, str]] = field(default_factory=list)
    inspect: list[tuple[str, str]] = field(default_factory=list)


def generate_us(snap: Snapshot, dates: list[date], *, universe_rule: str = "sp100",
                per_sector: int = PER_SECTOR) -> RunResult:
    """US cases under one universe rule: "sp100" (index members on each date) or
    "sector" (the per_sector largest of each GICS sector among the pool's companies
    that pass every filter, ranked by market cap on the valuation date)."""
    if universe_rule not in UNIVERSE_RULES:
        raise ValueError(f"universe_rule must be one of {UNIVERSE_RULES}")
    result = RunResult()
    industry_map = damodaran.load_industry_map(snap)["US"]
    if universe_rule == "sector":
        pool, pool_excluded = us_sector_candidates(snap)
        result.exclusions.extend(pool_excluded)
    for as_of in dates:
        ctx = UsContext(snap, as_of, industry_map)
        if universe_rule == "sector":
            candidates = pool
        else:
            candidates, excluded = us_candidates(snap, as_of, industry_map)
            result.exclusions.extend(excluded)
        built_by_ticker: dict[str, Built] = {}
        for cand in candidates:
            built = build_us_inputs(ctx, cand)
            if isinstance(built, Exclusion):
                result.exclusions.append(built)
                continue
            built_by_ticker[cand.ticker] = built
        if universe_rule == "sector":
            ranked = [(t, b.company.gics_sector or "", b.inputs.market_cap) for t, b in built_by_ticker.items()]
            kept = select_sector_top(ranked, per_sector)
            for ticker, built in list(built_by_ticker.items()):
                if ticker in kept:
                    built.notes["sector_rank"] = f"{kept[ticker]} of {built.company.gics_sector} by market cap on {as_of}"
                else:
                    result.exclusions.append(Exclusion("US", ticker, as_of, [f"outside_sector_top_{per_sector}"]))
                    del built_by_ticker[ticker]
        for cand in candidates:
            built = built_by_ticker.get(cand.ticker)
            if built is None:
                continue
            cases, failures = make_cases(built, as_of, snap.snapshot_id, US_POLICIES)
            base = next((c for c in cases if c.policy_label == "textbook"), None)
            if base is None or base.checkpoints.equity <= 0:
                # A negative value per share is computable but useless as a test case.
                result.exclusions.append(
                    Exclusion("US", cand.ticker, as_of, failures + ["dcf_equity_not_positive"]))
                continue
            if failures:
                result.exclusions.append(Exclusion("US", cand.ticker, as_of, failures))
            result.cases.extend(cases)
            result.fallbacks.extend((cand.ticker, as_of, f) for f in built.fallbacks)
            result.notes.extend((cand.ticker, as_of, key, str(value))
                                for key, value in built.notes.items())
            if any(f.startswith("lease_liability") and "tag_absent" in f for f in built.fallbacks):
                # After ASC 842 every lessee has the liability. No tag means it was not found.
                result.inspect.extend((c.case_id, "lease_liability_absent_after_asc842")
                                      for c in cases)
            for case in cases:
                ratio = case.checkpoints.ev / market_enterprise_value(built.inputs)
                if not EV_RATIO_BAND[0] <= ratio <= EV_RATIO_BAND[1]:
                    result.inspect.append((case.case_id, f"ev_over_market_ev={ratio:.2f}"))
                for warning in case.checkpoints.warnings:
                    if warning in ("equity_not_positive", "non_positive_flow"):
                        result.inspect.append((case.case_id, warning))
    return result


def mark_judgment_subset(cases: list[Case], size: int = JUDGMENT_SUBSET_SIZE,
                         seed: int = JUDGMENT_SEED) -> list[tuple[str, date]]:
    """Flag a fixed random subset of company-dates for the judgment tier.

    The draw is seeded and spread over the valuation dates in proportion to how many
    company-dates each has, so the same case set always gives the same subset.
    """
    by_date: dict[date, list[str]] = {}
    for case in cases:
        tickers = by_date.setdefault(case.valuation_date, [])
        if case.company.ticker not in tickers:
            tickers.append(case.company.ticker)
    total = sum(len(t) for t in by_date.values())
    days = sorted(by_date)
    if total <= size:
        quota = {day: len(by_date[day]) for day in days}
    else:
        # Largest remainders, so the quotas add up to the size exactly.
        exact = {day: size * len(by_date[day]) / total for day in days}
        quota = {day: int(exact[day]) for day in days}
        leftovers = sorted(days, key=lambda day: exact[day] - quota[day], reverse=True)
        for day in leftovers[: size - sum(quota.values())]:
            quota[day] += 1
    rng = random.Random(seed)
    chosen: list[tuple[str, date]] = []
    for day in days:
        chosen += [(ticker, day) for ticker in rng.sample(sorted(by_date[day]), quota[day])]
    picked = set(chosen)
    for case in cases:
        case.tier_variants.judgment = (case.company.ticker, case.valuation_date) in picked
    return sorted(chosen, key=lambda pair: (pair[1], pair[0]))


def write_run(result: RunResult, out_dir: Path) -> dict:
    """Write cases.jsonl, exclusions.csv, fallbacks.csv, inspect.csv and summary.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subset = mark_judgment_subset(result.cases)
    with open(out_dir / "judgment_subset.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "valuation_date"])
        writer.writerows(subset)
    with open(out_dir / "cases.jsonl", "w", encoding="utf-8") as handle:
        for case in result.cases:
            handle.write(case.model_dump_json() + "\n")
    with open(out_dir / "exclusions.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "ticker", "valuation_date", "reasons"])
        for e in result.exclusions:
            writer.writerow([e.market, e.ticker, e.valuation_date, ";".join(e.reasons)])
    with open(out_dir / "fallbacks.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "valuation_date", "fallback"])
        writer.writerows(result.fallbacks)
    with open(out_dir / "notes.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "valuation_date", "note", "value"])
        writer.writerows(result.notes)
    with open(out_dir / "inspect.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "reason"])
        writer.writerows(result.inspect)
    summary = summarize(result)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def summarize(result: RunResult) -> dict:
    by_date: dict[str, dict] = {}
    for case in result.cases:
        day = by_date.setdefault(case.valuation_date.isoformat(), {"firms": set(), "cases": 0})
        day["firms"].add(case.company.ticker)
        day["cases"] += 1
    reasons: dict[str, int] = {}
    for e in result.exclusions:
        for reason in e.reasons:
            code = reason.split(":")[0]
            reasons[code] = reasons.get(code, 0) + 1

    shown: dict[str, list[int]] = {}
    for case in result.cases:
        price = case.checkpoints.price_per_share
        for trap, answer in case.trap_answers.items():
            if answer is None or trap == case.policy_label:
                continue
            seen = shown.setdefault(trap, [0, 0])
            seen[0] += abs(answer - price) > TRAP_VISIBLE_REL * abs(price)
            seen[1] += 1

    def med(label: str, pick) -> float | None:
        values = [pick(c) for c in result.cases if c.policy_label == label]
        return round(statistics.median(values), 4) if values else None

    return {
        "cases": len(result.cases),
        "firms_by_date": {d: len(v["firms"]) for d, v in sorted(by_date.items())},
        "cases_by_date": {d: v["cases"] for d, v in sorted(by_date.items())},
        "exclusion_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "fallbacks_logged": len(result.fallbacks),
        "cases_to_inspect": len({case_id for case_id, _ in result.inspect}),
        "judgment_company_dates": len({(c.company.ticker, c.valuation_date)
                                       for c in result.cases if c.tier_variants.judgment}),
        # Share of cases where falling into the trap moves the price by more than 2 percent.
        "trap_visible_share": {trap: round(a / b, 3) for trap, (a, b) in sorted(shown.items())},
        "median_wacc": {label: med(label, lambda c: c.checkpoints.wacc)
                        for label in ("textbook", "practitioner")},
        "median_tv_share": {label: med(label, lambda c: c.checkpoints.tv_share)
                            for label in ("textbook", "practitioner")},
        "median_price_over_market": {
            label: med(label, lambda c: c.checkpoints.price_per_share / c.inputs.price)
            for label in ("textbook", "practitioner")},
    }
