"""Company universes.

United States, two rules:
- "sp100": S&P 100 constituents as of each valuation date, read from the Wikipedia
  revision of the "S&P 100" article that was live on that date (version zero).
- "sector": the largest US-exchange listings per GICS sector outside Financials. The
  candidate pool (data/universe/us_sector_seed.csv, the 30 largest per sector by market
  cap on October 4, 2026, from a Refinitiv screener export) is pulled in full; the
  generator then keeps, per sector and valuation date, the N largest by market cap on
  that date among the companies that pass every filter. The GICS classification is the
  one in force on the export day: there is no history in the export.
Korea: a hand-kept seed list of large KOSPI names in data/universe/kr_seed.csv,
because index membership needs a KRX login. DART confirms each code on fetch.
Japan: a hand-kept seed list of large TSE Prime names in data/universe/jp_seed.csv
with each company's fiscal year end month. The EDINET code is read off the daily
document index, which lists the security code of every filer.
GICS labels for every company of the three markets sit in data/universe/gics_labels.csv
(built by scripts/build_us_sector_seed.py) and are copied into each case's company block.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..config import UNIVERSE_DIR
from .http import Http
from .snapshot import Snapshot

WIKI_API = "https://en.wikipedia.org/w/api.php"
SP100_TITLE = "S&P 100"

# Old index tickers that live on under a new symbol. Tickers of companies that were
# acquired or taken private (AGN, RTN, WBA, ...) have no current symbol and no Yahoo
# price history, so they drop out with a reason code instead.
TICKER_ALIASES = {"FB": "META", "UTX": "RTX", "BK": "BNY"}

# Tickers whose history sits under an older SEC registrant than the one the ticker
# points to today. Exxon moved under a new holding company in 2026 and the new CIK
# carries only the filings made since.
CIK_OVERRIDES = {"XOM": "0000034088"}


def current_ticker(ticker: str) -> str:
    """The symbol a past index ticker trades under today, written the SEC way (BRK-B)."""
    symbol = ticker.strip().upper().replace(".", "-")
    return TICKER_ALIASES.get(symbol, symbol)


def cik_for(ticker: str, ticker_map: dict[str, str]) -> str | None:
    """CIK holding the filing history of a (current) ticker, or None if SEC lists none."""
    return CIK_OVERRIDES.get(ticker) or ticker_map.get(ticker)


def wiki_http() -> Http:
    return Http(min_interval=1.0, headers={"User-Agent": "dcfbench/0.0.1 (academic research)"})


@dataclass(frozen=True)
class Constituent:
    ticker: str
    name: str
    sector: str | None = None


def fetch_sp100(snap: Snapshot, http: Http, as_of: date) -> list[Constituent]:
    prefix = f"universe/sp100/{as_of.isoformat()}"
    raw = snap.fetch(f"{prefix}/revision.json", WIKI_API, http, params=dict(
        action="query", prop="revisions", titles=SP100_TITLE, rvlimit=1, rvdir="older",
        rvstart=f"{as_of.isoformat()}T23:59:59Z", rvprop="ids|timestamp", format="json",
        formatversion=2,
    ))
    revision = json.loads(raw)["query"]["pages"][0]["revisions"][0]
    snap.fetch(f"{prefix}/page.json", WIKI_API, http, params=dict(
        action="parse", oldid=revision["revid"], prop="text", format="json", formatversion=2,
    ))
    return load_sp100(snap, as_of)


def load_sp100(snap: Snapshot, as_of: date) -> list[Constituent]:
    html = snap.read_json(f"universe/sp100/{as_of.isoformat()}/page.json")["parse"]["text"]
    for table in pd.read_html(io.StringIO(html)):
        columns = {str(c).strip().lower(): c for c in table.columns}
        if "symbol" in columns and len(table) >= 90:
            name_col = columns.get("name")
            sector_col = columns.get("sector")
            return [
                Constituent(
                    str(row[columns["symbol"]]).strip(),
                    str(row[name_col]).strip() if name_col is not None else "",
                    str(row[sector_col]).strip() if sector_col is not None else None,
                )
                for _, row in table.iterrows()
            ]
    raise ValueError(f"no constituent table in the S&P 100 article as of {as_of}")


def sp100_revision(snap: Snapshot, as_of: date) -> dict:
    """Revision id and timestamp of the article version used for as_of."""
    raw = snap.read_json(f"universe/sp100/{as_of.isoformat()}/revision.json")
    return raw["query"]["pages"][0]["revisions"][0]


@dataclass(frozen=True)
class UsSectorSeed:
    ticker: str  # as the SEC writes it (BRK-B)
    name: str
    gics_sector: str
    gics_sub_industry: str
    market_cap_usd: float  # on the export day
    rank_in_sector: int


def load_us_sector_seed() -> list[UsSectorSeed]:
    path = UNIVERSE_DIR / "us_sector_seed.csv"
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        cap_column = next(c for c in reader.fieldnames if c.startswith("market_cap_usd"))
        return [UsSectorSeed(r["ticker"].strip(), r["name"], r["gics_sector"], r["gics_sub_industry"],
                             float(r[cap_column]), int(r["rank_in_sector"])) for r in reader]


@dataclass(frozen=True)
class GicsLabel:
    sector: str
    industry_group: str
    industry: str
    sub_industry: str
    sub_code: str


def load_gics_labels() -> dict[tuple[str, str], GicsLabel]:
    """(market, ticker) -> GICS names, for the companies the benchmark touches. Empty
    when the file is absent, so a case set can be built without it."""
    path = UNIVERSE_DIR / "gics_labels.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return {(r["market"], r["ticker"].strip()): GicsLabel(
            r["gics_sector"], r["gics_industry_group"], r["gics_industry"], r["gics_sub_industry"], r["gics_sub_code"])
            for r in csv.DictReader(handle)}


@dataclass(frozen=True)
class KrSeed:
    stock_code: str  # 6 digits
    name: str
    yahoo_suffix: str  # KS for KOSPI, KQ for KOSDAQ
    note: str = ""

    @property
    def yahoo_ticker(self) -> str:
        return f"{self.stock_code}.{self.yahoo_suffix}"


SEED_UNIVERSES = ("seed", "all")  # the hand-kept list alone, or with the sector additions


def _seed_files(stem: str, universe: str) -> list[Path]:
    """kr_seed.csv alone, or followed by kr_seed_sector.csv (the per-sector additions
    of October 5, 2026, built by scripts/build_kr_jp_sector_seeds.py) when it exists."""
    if universe not in SEED_UNIVERSES:
        raise ValueError(f"universe must be one of {SEED_UNIVERSES}")
    files = [UNIVERSE_DIR / f"{stem}.csv"]
    extra = UNIVERSE_DIR / f"{stem}_sector.csv"
    if universe == "all" and extra.exists():
        files.append(extra)
    return files


def load_kr_seed(universe: str = "seed") -> list[KrSeed]:
    out: list[KrSeed] = []
    seen: set[str] = set()
    for path in _seed_files("kr_seed", universe):
        # utf-8-sig: Excel writes a byte order mark. A short row leaves the note as None.
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                code = r["stock_code"].zfill(6)
                if code in seen:
                    continue
                seen.add(code)
                out.append(KrSeed(code, r["name"], r["yahoo_suffix"], r.get("note") or ""))
    return out


@dataclass(frozen=True)
class JpSeed:
    security_code: str  # 4 characters as on the exchange, "7203"
    name: str
    industry: str  # Damodaran industry group, as the betaJapan file writes it
    fye_month: int
    note: str = ""

    @property
    def yahoo_ticker(self) -> str:
        return f"{self.security_code}.T"


def load_jp_seed(universe: str = "seed") -> list[JpSeed]:
    out: list[JpSeed] = []
    seen: set[str] = set()
    for path in _seed_files("jp_seed", universe):
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for r in csv.DictReader(handle):
                code = r["security_code"].strip()
                if code in seen:
                    continue
                seen.add(code)
                out.append(JpSeed(code, r["name"], r["industry"], int(r["fye_month"]), r.get("note") or ""))
    return out
