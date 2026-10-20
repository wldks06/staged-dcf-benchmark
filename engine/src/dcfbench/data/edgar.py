"""SEC EDGAR: company facts, submissions, tag fallbacks, as-of filter.

fetch_* functions go to the network through the snapshot, load_* functions read the snapshot only.

How a number is picked:
- Annual facts come from 10-K and 10-K/A filings. A fact belongs to a fiscal year by
  its period dates. Neither fy nor fp is used: fy is the fiscal year of the filing,
  not of the period, and some filers label their annual report "Q4" instead of "FY".
- A fact is visible on date d if filed <= d. Among visible facts for a period the
  latest filed wins, so a restatement known on d replaces the original.
- Each input has an ordered list of recipes (INPUTS below). For a multi-year input
  the first recipe that covers every year of the window wins, so the same tags are
  used across the window. If none does, each year takes its own first match and the
  mix is logged. Every fallback is logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import secret
from ..schema import Provenance
from .http import Http
from .recipes import R, Match, Recipe, T, resolve
from .snapshot import Snapshot

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

ANNUAL_FORMS = ("10-K", "10-K/A")
PERIODIC_FORMS = ANNUAL_FORMS + ("10-Q", "10-Q/A")
ANNUAL_DAYS = (350, 380)
ASC842_FIRST_YEAR_END = date(2019, 12, 15)  # operating lease liabilities are on the balance sheet from here


def pad_cik(cik: str | int) -> str:
    return str(int(cik)).zfill(10)


def normalize_ticker(ticker: str) -> str:
    """SEC writes share classes with a dash (BRK-B), index providers with a dot (BRK.B)."""
    return ticker.strip().upper().replace(".", "-")


# --- Fetch (network, through the snapshot) -------------------------------------


def sec_http() -> Http:
    # SEC allows 10 requests per second and requires a contact in the User-Agent.
    return Http(min_interval=0.125, headers={
        "User-Agent": secret("SEC_USER_AGENT"),
        "Accept-Encoding": "gzip, deflate",
    })


def fetch_ticker_map(snap: Snapshot, http: Http) -> dict[str, str]:
    snap.fetch("edgar/company_tickers.json", TICKERS_URL, http)
    return load_ticker_map(snap)


def fetch_company(snap: Snapshot, http: Http, cik: str) -> None:
    """Submissions (all pages) and company facts for one company."""
    cik = pad_cik(cik)
    name = f"CIK{cik}.json"
    raw = snap.fetch(f"edgar/submissions/{name}", SUBMISSIONS_URL.format(name=name), http)
    for older in json.loads(raw)["filings"].get("files", []):
        snap.fetch(f"edgar/submissions/{older['name']}",
                   SUBMISSIONS_URL.format(name=older["name"]), http)
    snap.fetch(f"edgar/companyfacts/{name}", FACTS_URL.format(cik=cik), http)


# --- Load (snapshot only) --------------------------------------------------------


def load_ticker_map(snap: Snapshot) -> dict[str, str]:
    rows = snap.read_json("edgar/company_tickers.json").values()
    return {normalize_ticker(r["ticker"]): pad_cik(r["cik_str"]) for r in rows}


def load_submissions(snap: Snapshot, cik: str) -> dict:
    return snap.read_json(f"edgar/submissions/CIK{pad_cik(cik)}.json")


@dataclass(frozen=True)
class Filing:
    accn: str
    form: str
    filed: date
    report_date: date | None
    primary_document: str


def load_filings(snap: Snapshot, cik: str, as_of: date,
                 forms: tuple[str, ...] = PERIODIC_FORMS) -> list[Filing]:
    """Filings of the given forms filed on or before as_of, newest first."""
    submissions = load_submissions(snap, cik)
    pages = [submissions["filings"]["recent"]]
    for older in submissions["filings"].get("files", []):
        pages.append(snap.read_json(f"edgar/submissions/{older['name']}"))
    out = []
    for page in pages:
        for i, form in enumerate(page["form"]):
            filed = date.fromisoformat(page["filingDate"][i])
            if form in forms and filed <= as_of:
                report = page["reportDate"][i]
                out.append(Filing(page["accessionNumber"][i], form, filed,
                                  date.fromisoformat(report) if report else None,
                                  page["primaryDocument"][i]))
    return sorted(out, key=lambda f: (f.filed, f.accn), reverse=True)


def load_facts(snap: Snapshot, cik: str) -> "FactStore":
    return FactStore(snap.read_json(f"edgar/companyfacts/CIK{pad_cik(cik)}.json"))


# --- Facts with an as-of filter ---------------------------------------------------


@dataclass(frozen=True)
class Fact:
    taxonomy: str
    tag: str
    unit: str
    value: float
    start: date | None
    end: date
    accn: str
    filed: date
    form: str
    fp: str | None

    @property
    def is_annual(self) -> bool:
        if self.start is None:
            return False
        return ANNUAL_DAYS[0] <= (self.end - self.start).days <= ANNUAL_DAYS[1]

    def provenance(self, note: str | None = None) -> list[Provenance]:
        return [Provenance(
            source="edgar", tag=f"{self.taxonomy}:{self.tag}", value=self.value, accn=self.accn,
            filed=self.filed, form=self.form, period_end=self.end, note=note,
        )]


@dataclass(frozen=True)
class Derived:
    """A value built from other resolved inputs, used as a term in a recipe."""

    value: float
    items: tuple[Provenance, ...]

    def provenance(self, note: str | None = None) -> list[Provenance]:
        return list(self.items)


class FactStore:
    """The companyfacts JSON of one company, queried as of a date."""

    def __init__(self, companyfacts: dict):
        self.cik = pad_cik(companyfacts["cik"])
        self.name = companyfacts.get("entityName", "")
        self._raw = companyfacts.get("facts", {})
        self._cache: dict[tuple[str, str], list[Fact]] = {}

    def _all(self, taxonomy: str, tag: str) -> list[Fact]:
        key = (taxonomy, tag)
        if key not in self._cache:
            facts = []
            units = self._raw.get(taxonomy, {}).get(tag, {}).get("units", {})
            for unit, rows in units.items():
                for row in rows:
                    if row.get("val") is None or not row.get("filed") or not row.get("form"):
                        continue
                    start = row.get("start")
                    facts.append(Fact(
                        taxonomy, tag, unit, float(row["val"]),
                        date.fromisoformat(start) if start else None,
                        date.fromisoformat(row["end"]), row["accn"],
                        date.fromisoformat(row["filed"]), row["form"], row.get("fp"),
                    ))
            self._cache[key] = facts
        return self._cache[key]

    def facts(self, tag: str, as_of: date, *, taxonomy: str = "us-gaap", unit: str | None = None,
              forms: tuple[str, ...] | None = None) -> list[Fact]:
        """Every fact for a tag that was filed on or before as_of."""
        return [f for f in self._all(taxonomy, tag)
                if f.filed <= as_of
                and (unit is None or f.unit == unit)
                and (forms is None or f.form in forms)]

    @staticmethod
    def _latest_filed(candidates: list[Fact]) -> Fact | None:
        return max(candidates, key=lambda f: (f.filed, f.accn)) if candidates else None

    def annual(self, tag: str, end: date, as_of: date, *, unit: str = "USD",
               taxonomy: str = "us-gaap") -> Fact | None:
        """The fiscal-year value for the year ending on end, as known on as_of."""
        return self._latest_filed([
            f for f in self.facts(tag, as_of, taxonomy=taxonomy, unit=unit, forms=ANNUAL_FORMS)
            if f.end == end and f.is_annual
        ])

    def instant(self, tag: str, end: date, as_of: date, *, unit: str = "USD",
                taxonomy: str = "us-gaap") -> Fact | None:
        """The balance at end as reported in an annual filing, as known on as_of."""
        return self._latest_filed([
            f for f in self.facts(tag, as_of, taxonomy=taxonomy, unit=unit, forms=ANNUAL_FORMS)
            if f.end == end and f.start is None
        ])

    def restated_from(self, chosen: Fact, as_of: date) -> list[Fact]:
        """Earlier visible filings that reported a different value for the same period."""
        same_period = [
            f for f in self.facts(chosen.tag, as_of, taxonomy=chosen.taxonomy, unit=chosen.unit,
                                  forms=ANNUAL_FORMS)
            if f.end == chosen.end and f.start == chosen.start and f.value != chosen.value
        ]
        seen, out = set(), []
        for f in sorted(same_period, key=lambda f: f.filed):
            if f.value not in seen:
                seen.add(f.value)
                out.append(f)
        return out

    def fiscal_year_ends(self, as_of: date, count: int) -> list[date]:
        """The last `count` fiscal year ends with an annual filing on or before as_of, newest first."""
        ends: set[date] = set()
        for tag in REVENUE_TAGS + ("NetIncomeLoss", "IncomeTaxExpenseBenefit"):
            for f in self.facts(tag, as_of, unit="USD", forms=ANNUAL_FORMS):
                if f.is_annual:
                    ends.add(f.end)
        chain: list[date] = []
        for end in sorted(ends, reverse=True):
            # Keep a chain of year ends about twelve months apart.
            if not chain or ANNUAL_DAYS[0] <= (chain[-1] - end).days <= ANNUAL_DAYS[1]:
                chain.append(end)
            if len(chain) == count:
                break
        return chain


# --- Inputs and their fallback recipes ----------------------------------------------

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RegulatedAndUnregulatedOperatingRevenue",  # [+] utilities
)

_SHORT_TERM_DEBT_TAGS = ("ShortTermBorrowings", "NotesAndLoansPayableCurrent", "CommercialPaper",
                         "NotesPayableCurrent")
_SHORT_TERM_DEBT = T(*_SHORT_TERM_DEBT_TAGS, optional=True)


@dataclass(frozen=True)
class InputSpec:
    kind: str  # "duration" or "instant"
    recipes: list[Recipe]
    unit: str = "USD"
    # "required": the case is excluded without it. "zero": absent means none, stored as 0
    # with a note. "none": absent stays None and only the policies that need it are affected.
    if_absent: str = "required"
    # "first": the first complete recipe wins. "largest": every recipe is a candidate total
    # and the largest wins, for concepts where a narrower tag can shadow the full amount.
    pick: str = "first"


# Preferred tag first. Tags added while fitting the sample are marked [+].
INPUTS: dict[str, InputSpec] = {
    "revenue": InputSpec("duration", [R(tag) for tag in REVENUE_TAGS]),
    "pretax_income": InputSpec("duration", [
        R("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
        R("IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
        # [+] only the domestic and foreign halves are tagged; a utility with no foreign
        # operations tags the domestic half alone (Eversource, NiSource)
        R("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
          T("IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign", optional=True)),
    ]),
    "interest_expense": InputSpec("duration", [
        R("InterestExpense"),
        R("InterestExpenseNonoperating"),  # [+] replaced InterestExpense in recent taxonomies
        R("InterestAndDebtExpense"),  # [+]
        R("InterestExpenseDebt"),
        R("InterestExpenseOperating"),  # [+]
        R("InterestPaidNet"),
        R("InterestPaid"),  # [+]
    ]),
    # ebit is resolved after pretax_income and interest_expense because its fallback uses them.
    "ebit": InputSpec("duration", [
        R("OperatingIncomeLoss"),
        R("@pretax_income", "@interest_expense"),
    ]),
    # Several companies tag a small sub-item with one of the broad D&A tags (Intel,
    # McDonald's) or split depreciation from amortization (Gilead), so the first match can
    # be a fraction of the true total. The largest candidate total is taken instead.
    "da": InputSpec("duration", [
        R("DepreciationDepletionAndAmortization"),
        R("DepreciationAndAmortization"),
        R("DepreciationAmortizationAndAccretionNet"),
        R("Depreciation", "AmortizationOfIntangibleAssets"),  # [+] the two halves reported apart
        R("Depreciation", "AdjustmentForAmortization"),  # [+]
        R("Depreciation"),
        R("CostOfGoodsAndServicesSoldDepreciationAndAmortization"),  # [+] shown inside cost of sales (PSEG, MPLX)
    ], pick="largest"),
    "capex": InputSpec("duration", [
        R("PaymentsToAcquirePropertyPlantAndEquipment"),
        R("PaymentsToAcquireProductiveAssets"),
        R("PaymentsToAcquireOtherPropertyPlantAndEquipment"),  # [+]
        R("PaymentsToAcquireOtherProductiveAssets"),  # [+]
        R("PaymentsForCapitalImprovements"),  # [+] Corning's name for it
    ]),
    "tax_expense": InputSpec("duration", [R("IncomeTaxExpenseBenefit")]),
    "sbc": InputSpec("duration", [
        R("ShareBasedCompensation"),
        R("AllocatedShareBasedCompensationExpense"),
    ], if_absent="none"),
    "shares_diluted": InputSpec("duration", [
        R("WeightedAverageNumberOfDilutedSharesOutstanding"),
        R("WeightedAverageNumberOfShareOutstandingBasicAndDiluted"),  # [+]
    ], unit="shares"),
    "receivables": InputSpec("instant", [
        R("AccountsReceivableNetCurrent"),
        R("AccountsNotesAndLoansReceivableNetCurrent"),  # [+] this and the ones below
        R("ReceivablesNetCurrent"),
        R("AccountsAndOtherReceivablesNetCurrent"),
        R("AccountsReceivableNet"),
        R("AccountsAndNotesReceivableNet"),
    ]),
    "inventory": InputSpec("instant", [
        R("InventoryNet"),
        # [+] An audit against the filings found inventory under other tags: Boeing,
        # Exxon (19 billion read as zero), Union Pacific, Southern.
        R("InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"),
        R("EnergyRelatedInventory", T("InventoryPartsAndComponentsNetOfReserves", optional=True)),
        R("MaterialsSuppliesAndOther"),
        R("OtherInventorySupplies", T("EnergyRelatedInventoryOtherFossilFuel", optional=True),
          T("EnergyRelatedInventoryNaturalGasInStorage", optional=True)),
    ], if_absent="zero"),
    "payables": InputSpec("instant", [
        R("AccountsPayableCurrent"),
        R("AccountsPayableTradeCurrent"),  # [+] this and the ones below
        R("AccountsPayableAndAccruedLiabilitiesCurrent"),
        R("AccountsPayableCurrentAndNoncurrent"),
    ]),
    "cash": InputSpec("instant", [
        R("CashAndCashEquivalentsAtCarryingValue"),
        R("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        R("CashAndCashEquivalentsAtCarryingValueIncludingDiscontinuedOperations"),  # [+]
        R("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations"),  # [+]
        R("Cash"),  # [+]
    ]),
    "st_investments": InputSpec("instant", [
        R("ShortTermInvestments"),
        R("MarketableSecuritiesCurrent"),
        R("AvailableForSaleSecuritiesDebtSecuritiesCurrent"),
    ], if_absent="zero"),
    # Total borrowings. The tags are listed below; the recipes below add them up without
    # double counting: DebtCurrent already contains the current part of long-term debt.
    "debt_total": InputSpec("instant", [
        R("DebtLongtermAndShorttermCombinedAmount"),
        R("LongTermDebtNoncurrent", "DebtCurrent"),
        R("LongTermDebtAndCapitalLeaseObligations", "DebtCurrent"),  # [+]
        R("LongTermDebtNoncurrent", T("LongTermDebtCurrent", optional=True), _SHORT_TERM_DEBT),
        R("LongTermDebtAndCapitalLeaseObligations",
          T("LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtCurrent", optional=True),
          _SHORT_TERM_DEBT),
        R("LongTermDebt", _SHORT_TERM_DEBT),
        R("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", _SHORT_TERM_DEBT),  # [+]
        R(T("ConvertibleLongTermNotesPayable", "ConvertibleNotesPayable", "LongTermNotesPayable",
            "SeniorNotes"), _SHORT_TERM_DEBT),  # [+]
        R(T(*_SHORT_TERM_DEBT_TAGS)),  # [+] short-term borrowings only
    ]),
    "lease_liability": InputSpec("instant", [
        R("OperatingLeaseLiability"),
        R("OperatingLeaseLiabilityNoncurrent", T("OperatingLeaseLiabilityCurrent", optional=True)),
        # [+] McDonald's shows operating and finance leases as one balance sheet line from
        # FY2024. The operating part is still in the maturity table: payments due less
        # the undiscounted excess.
        R("LesseeOperatingLeaseLiabilityPaymentsDue",
          T("LesseeOperatingLeaseLiabilityUndiscountedExcessAmount", sign=-1)),
    ], if_absent="zero"),
    "preferred": InputSpec("instant", [R("PreferredStockValue")], if_absent="zero"),
    "minority_interest": InputSpec("instant", [R("MinorityInterest")], if_absent="zero"),
    "book_equity": InputSpec("instant", [
        R("StockholdersEquity"),
        R("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ], if_absent="none"),
    "total_liabilities": InputSpec("instant", [R("Liabilities")], if_absent="none"),
}

# Inputs taken for each of the fiscal years in the window, the rest only at the last year end.
SERIES_INPUTS = (
    "revenue", "pretax_income", "interest_expense", "ebit", "da", "capex", "tax_expense", "sbc",
    "receivables", "inventory", "payables",
)
SCALAR_INPUTS = (
    "shares_diluted", "cash", "st_investments", "debt_total", "lease_liability", "preferred",
    "minority_interest", "book_equity", "total_liabilities",
)
NO_DEBT_NOTE = "no_borrowing_tags_assumed_zero"
NEGLIGIBLE_INTEREST_SHARE = 0.01  # of EBIT


@dataclass
class Resolved:
    value: float | None
    provenance: list[Provenance] = field(default_factory=list)
    recipe: int | None = None  # 0 is the first choice, higher numbers are fallbacks
    note: str | None = None


@dataclass
class CompanyInputs:
    cik: str
    as_of: date
    fiscal_year_ends: list[date]  # oldest to newest
    series: dict[str, list[Resolved]]
    scalars: dict[str, Resolved]
    prior_nwc: dict[str, Resolved]  # working capital parts one year before the window
    issues: list[str]  # reason codes that exclude the case
    fallbacks: list[str]  # every fallback or assumed zero, for the log


def fiscal_year_label(end: date) -> str:
    """A year ending in the first days of January belongs to the year before."""
    return str((end - timedelta(days=15)).year)


def _describe(match: Match) -> str:
    return " + ".join(("-" if p.sign < 0 else "") + p.concept for p in match.parts)


def _zero(end: date, reason: str) -> Resolved:
    item = Provenance(source="derived", value=0.0, period_end=end,
                      fiscal_year=fiscal_year_label(end), note=reason)
    return Resolved(0.0, [item], note=reason)


class _Resolver:
    def __init__(self, store: FactStore, as_of: date):
        self.store = store
        self.as_of = as_of
        self.done: dict[tuple[str, date], Resolved] = {}
        self.fallbacks: list[str] = []

    def _lookup(self, spec: InputSpec, end: date):
        def lookup(concept: str):
            if concept.startswith("@"):
                prior = self.done.get((concept[1:], end))
                if prior is None or prior.value is None:
                    return None
                return Derived(prior.value, tuple(prior.provenance))
            getter = self.store.annual if spec.kind == "duration" else self.store.instant
            return getter(concept, end, self.as_of, unit=spec.unit)
        return lookup

    def _from_match(self, name: str, end: date, match: Match, index: int, log: bool) -> Resolved:
        year = fiscal_year_label(end)
        items: list[Provenance] = []
        for part in match.parts:
            note = "subtracted" if part.sign < 0 else None
            for item in part.fact.provenance(note):
                items.append(item.model_copy(update={"fiscal_year": year}))
            if isinstance(part.fact, Fact):
                for old in self.store.restated_from(part.fact, self.as_of):
                    items.append(Provenance(
                        source="edgar", tag=f"{old.taxonomy}:{old.tag}", value=old.value,
                        accn=old.accn, filed=old.filed, form=old.form, period_end=old.end,
                        fiscal_year=year, note="superseded by a later filing",
                    ))
        if index > 0 and log:
            self.fallbacks.append(f"{name}:{year}:fallback_{index}:{_describe(match)}")
        return Resolved(match.value, items, index)

    def _absent(self, name: str, end: date, log: bool) -> Resolved:
        if INPUTS[name].if_absent != "zero":
            return Resolved(None, note="tag_absent")
        reason = "tag_absent_assumed_zero"
        if name == "lease_liability" and end < ASC842_FIRST_YEAR_END:
            reason = "pre_asc842_assumed_zero"
        if log:
            self.fallbacks.append(f"{name}:{fiscal_year_label(end)}:{reason}")
        return _zero(end, reason)

    def _match(self, spec: InputSpec, end: date) -> Match | None:
        lookup = self._lookup(spec, end)
        if spec.pick == "first":
            return resolve(spec.recipes, lookup)
        best = None
        for index, recipe in enumerate(spec.recipes):
            match = resolve([recipe], lookup)
            if match is not None and (best is None or match.value > best.value):
                match.recipe_index = index
                best = match
        return best

    def resolve(self, name: str, end: date, *, log: bool = True) -> Resolved:
        match = self._match(INPUTS[name], end)
        out = (self._absent(name, end, log) if match is None
               else self._from_match(name, end, match, match.recipe_index, log))
        self.done[(name, end)] = out
        return out

    def resolve_series(self, name: str, ends: list[date]) -> list[Resolved]:
        """One value per year, from the same recipe for every year when one covers them all."""
        spec = INPUTS[name]
        if spec.pick == "largest":
            return [self.resolve(name, end) for end in ends]
        for index, recipe in enumerate(spec.recipes):
            matches = [resolve([recipe], self._lookup(spec, end)) for end in ends]
            if all(m is not None for m in matches):
                out = [self._from_match(name, end, m, index, True) for end, m in zip(ends, matches)]
                for end, resolved in zip(ends, out):
                    self.done[(name, end)] = resolved
                return out
        out = [self.resolve(name, end) for end in ends]
        if len({r.recipe for r in out if r.recipe is not None}) > 1:
            self.fallbacks.append(f"{name}:window:mixed_tags_across_years")
        return out


def _from_fact(fact: Fact, end: date, recipe: int) -> Resolved:
    year = fiscal_year_label(end)
    return Resolved(fact.value, [p.model_copy(update={"fiscal_year": year})
                                 for p in fact.provenance()], recipe)


def shares_outstanding(store: FactStore, as_of: date,
                       latest_end: date) -> tuple[Resolved, str | None]:
    """Shares outstanding from the cover page of the latest annual filing.

    Companies with several share classes report the cover count per class, which the
    companyfacts API leaves out. The fallbacks are the balance sheet count at year
    end, then the weighted average basic count of the year.
    Returns the value and, when a fallback was used, its log line.
    """
    year = fiscal_year_label(latest_end)
    cover = [
        f for f in store.facts("EntityCommonStockSharesOutstanding", as_of, taxonomy="dei",
                               unit="shares", forms=ANNUAL_FORMS)
        if latest_end <= f.end <= latest_end + timedelta(days=120)
    ]
    if cover:
        return _from_fact(max(cover, key=lambda f: (f.filed, f.end, f.accn)), latest_end, 0), None
    fact = store.instant("CommonStockSharesOutstanding", latest_end, as_of, unit="shares")
    if fact is not None:
        return (_from_fact(fact, latest_end, 1),
                f"shares_basic:{year}:fallback_1:CommonStockSharesOutstanding")
    fact = store.annual("WeightedAverageNumberOfSharesOutstandingBasic", latest_end, as_of,
                        unit="shares")
    if fact is not None:
        return (_from_fact(fact, latest_end, 2),
                f"shares_basic:{year}:fallback_2:WeightedAverageNumberOfSharesOutstandingBasic")
    return Resolved(None, note="tag_absent"), None


def diluted_shares_from_eps(store: FactStore, as_of: date, end: date) -> Resolved | None:
    """Net income over diluted EPS, for companies that tag diluted shares per class only."""
    income = store.annual("NetIncomeLoss", end, as_of)
    eps = store.annual("EarningsPerShareDiluted", end, as_of, unit="USD/shares")
    if income is None or eps is None or eps.value <= 0 or income.value <= 0:
        return None
    year = fiscal_year_label(end)
    items = [p.model_copy(update={"fiscal_year": year})
             for p in income.provenance() + eps.provenance("divisor")]
    return Resolved(income.value / eps.value, items, len(INPUTS["shares_diluted"].recipes))


def diluted_shares(store: FactStore, as_of: date, latest_end: date) -> Resolved:
    """Weighted average diluted shares of the last fiscal year, with the fallbacks."""
    resolved = _Resolver(store, as_of).resolve("shares_diluted", latest_end, log=False)
    if resolved.value is None:
        return diluted_shares_from_eps(store, as_of, latest_end) or resolved
    return resolved


def resolve_company(store: FactStore, as_of: date, *, years: int = 3) -> CompanyInputs:
    """Every EDGAR-sourced input for one company as known on as_of."""
    ends_desc = store.fiscal_year_ends(as_of, years + 1)
    resolver = _Resolver(store, as_of)
    if len(ends_desc) < years:
        return CompanyInputs(store.cik, as_of, sorted(ends_desc), {}, {}, {},
                             [f"only_{len(ends_desc)}_fiscal_years"], [])

    ends = sorted(ends_desc[:years])
    latest = ends[-1]
    year = fiscal_year_label(latest)
    series = {name: resolver.resolve_series(name, ends) for name in SERIES_INPUTS}
    scalars = {name: resolver.resolve(name, latest) for name in SCALAR_INPUTS}

    if scalars["shares_diluted"].value is None:
        derived = diluted_shares_from_eps(store, as_of, latest)
        if derived is not None:
            scalars["shares_diluted"] = derived
            resolver.done[("shares_diluted", latest)] = derived
            resolver.fallbacks.append(
                f"shares_diluted:{year}:fallback_{derived.recipe}:NetIncomeLoss / EarningsPerShareDiluted")

    shares, fallback = shares_outstanding(store, as_of, latest)
    scalars["shares_basic"] = shares
    if fallback:
        resolver.fallbacks.append(fallback)

    # No borrowing tag at the last year end: the company is debt-free if that year's
    # interest expense is absent or negligible next to EBIT. Material interest without a
    # recognizable debt tag is a tagging gap, and the case stays excluded.
    interest = series["interest_expense"]
    last_interest, last_ebit = interest[-1].value, series["ebit"][-1].value
    negligible = last_interest is None or (
        last_ebit is not None and last_ebit > 0
        and last_interest < NEGLIGIBLE_INTEREST_SHARE * last_ebit)
    if scalars["debt_total"].value is None and negligible:
        scalars["debt_total"] = _zero(latest, NO_DEBT_NOTE)
        resolver.fallbacks.append(f"debt_total:{year}:{NO_DEBT_NOTE}")
        series["interest_expense"] = [
            r if r.value is not None else _zero(end, NO_DEBT_NOTE)
            for end, r in zip(ends, interest)]
        for end, resolved in zip(ends, series["interest_expense"]):
            resolver.done[("interest_expense", end)] = resolved
        if any(r.value is None for r in series["ebit"]):  # its fallback needs interest
            series["ebit"] = resolver.resolve_series("ebit", ends)

    issues = []
    for name in SERIES_INPUTS:
        if INPUTS[name].if_absent == "required":
            issues += [f"missing_{name}:{fiscal_year_label(end)}"
                       for end, r in zip(ends, series[name]) if r.value is None]
    for name in (*SCALAR_INPUTS, "shares_basic"):
        required = name == "shares_basic" or INPUTS[name].if_absent == "required"
        if required and scalars[name].value is None:
            issues.append(f"missing_{name}:{year}")

    # The year before the window, for the change in working capital of the first year.
    prior_nwc: dict[str, Resolved] = {}
    if len(ends_desc) > years:
        for name in ("receivables", "inventory", "payables"):
            prior_nwc[name] = resolver.resolve(name, ends_desc[years], log=False)

    return CompanyInputs(store.cik, as_of, ends, series, scalars, prior_nwc, issues,
                         resolver.fallbacks)
