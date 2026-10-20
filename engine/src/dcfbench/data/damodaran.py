"""Damodaran data pages (NYU Stern).

Each January he publishes industry betas, default spreads by rating, country risk
premiums and the implied equity risk premium. Files are stored per January update.
january_year() picks the update nearest a valuation date: for 2022-12-31 that is
the January 2023 file, which is built on data through the end of 2022 but was
published a few days after the valuation date.

Archive naming on his site: archives/betas22.xls is the January 2023 update.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .http import FetchError, Http
from .snapshot import Snapshot

BASE = "https://pages.stern.nyu.edu/~adamodar/pc"
# Spread by rating for each January from 2015 to 2025 in one file. Later Januaries
# come from the live ratings.xls, which carries the current year's table.
SPREAD_HISTORY_FILE = "archives/bondspreads24.xlsx"
SPREAD_HISTORY_LAST_YEAR = 2025

US_EXCHANGE_PREFIXES = ("NYSE", "Nasdaq", "BATS")
KR_EXCHANGES = ("KOSE", "KOSDAQ")
JP_EXCHANGE = "TSE"


def damodaran_http() -> Http:
    return Http(min_interval=1.0, timeout=180.0)


def january_year(valuation_date: date) -> int:
    """Year of the January update nearest the valuation date."""
    return valuation_date.year + 1 if valuation_date.month >= 7 else valuation_date.year


def year_end(valuation_date: date) -> int:
    """Year whose end is nearest the valuation date, for the year-end series."""
    return valuation_date.year if valuation_date.month >= 7 else valuation_date.year - 1


# --- Fetch ------------------------------------------------------------------------


def _fetch_first(snap: Snapshot, http: Http, key: str, urls: list[str]) -> None:
    """Store the first URL that exists. His archive lags, so the newest year is the live file."""
    if snap.has(key):
        return
    error: FetchError | None = None
    for url in urls:
        try:
            snap.fetch(key, url, http)
            return
        except FetchError as exc:
            error = exc
    raise error


def fetch_betas(snap: Snapshot, http: Http, jan_year: int, *, region: str = "us") -> None:
    stem = {"us": "betas", "emerging": "betaemerg", "global": "betaGlobal", "japan": "betaJapan"}[region]
    yy = f"{(jan_year - 1) % 100:02d}"
    _fetch_first(snap, http, f"damodaran/{stem}/{jan_year}.xls",
                 [f"{BASE}/archives/{stem}{yy}.xls", f"{BASE}/datasets/{stem}.xls"])


def fetch_country_premiums(snap: Snapshot, http: Http, jan_year: int) -> None:
    yy = f"{(jan_year - 1) % 100:02d}"
    _fetch_first(snap, http, f"damodaran/ctryprem/{jan_year}", [
        f"{BASE}/archives/ctryprem{yy}.xlsx", f"{BASE}/archives/ctryprem{yy}.xls",
        f"{BASE}/datasets/ctryprem.xlsx",
    ])


def fetch_common(snap: Snapshot, http: Http) -> None:
    """Files that are not per-year: spreads, rating table, implied ERP, industry map."""
    snap.fetch("damodaran/bondspreads.xlsx", f"{BASE}/{SPREAD_HISTORY_FILE}", http)
    snap.fetch("damodaran/ratings.xls", f"{BASE}/ratings.xls", http)
    snap.fetch("damodaran/histimpl.xls", f"{BASE}/datasets/histimpl.xls", http)
    snap.fetch("damodaran/indname.xls", f"{BASE}/datasets/indname.xls", http)


# --- Parse --------------------------------------------------------------------------


def _sheet(content: bytes, sheet) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)


def _clean(value) -> str:
    """Collapse whitespace. His headers vary by year ('Industry  Name', 'Beta ')."""
    return " ".join(str(value).split())


def _header_row(df: pd.DataFrame, label: str) -> int:
    for i, value in enumerate(df.iloc[:, 0]):
        if isinstance(value, str) and _clean(value) == label:
            return i
    raise ValueError(f"no row starting with {label!r}")


def _table(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """The block under the header row whose first cell is label, with cleaned column names."""
    header = _header_row(df, label)
    table = df.iloc[header + 1:].copy()
    table.columns = [_clean(c) for c in df.iloc[header]]
    return table[table.iloc[:, 0].notna()]


@dataclass(frozen=True)
class IndustryBeta:
    industry: str
    unlevered: float
    unlevered_cash_corrected: float
    levered: float
    firms: int
    date_updated: date
    key: str  # snapshot key of the file


def load_industry_betas(snap: Snapshot, jan_year: int, *, region: str = "us") -> dict[str, IndustryBeta]:
    stem = {"us": "betas", "emerging": "betaemerg", "global": "betaGlobal", "japan": "betaJapan"}[region]
    key = f"damodaran/{stem}/{jan_year}.xls"
    df = _sheet(snap.read(key), "Industry Averages")
    updated = pd.Timestamp(df.iloc[0, 1]).date()
    if updated.year != jan_year:
        raise ValueError(f"{key} is dated {updated}, expected the January {jan_year} update")
    out = {}
    for _, row in _table(df, "Industry Name").iterrows():
        name = str(row["Industry Name"]).strip()
        try:
            out[name] = IndustryBeta(
                name, float(row["Unlevered beta"]),
                float(row["Unlevered beta corrected for cash"]), float(row["Beta"]),
                int(row["Number of firms"]), updated, key,
            )
        except (TypeError, ValueError):
            continue  # footer rows
    return out


def load_rating_table(snap: Snapshot) -> list[tuple[float, str, float]]:
    """(lower bound of interest coverage, rating, spread) for large non-financial firms.

    Rows are sorted by the lower bound. The spread column is the live year's table.
    """
    df = _sheet(snap.read("damodaran/ratings.xls"), 0)
    start = next(i for i, v in enumerate(df.iloc[:, 0]) if isinstance(v, str) and v.strip() == ">")
    rows = []
    for _, row in df.iloc[start + 1:].iterrows():
        if pd.isna(row[0]) or not isinstance(row[2], str):
            break
        rows.append((float(row[0]), row[2].strip(), float(row[3])))
    return sorted(rows)


def synthetic_rating(interest_coverage: float, table: list[tuple[float, str, float]]) -> str:
    """Rating label such as 'A2/A' for an interest coverage ratio (EBIT over interest)."""
    rating = table[0][1]
    for lower, label, _ in table:
        if interest_coverage >= lower:
            rating = label
    return rating


def load_spreads(snap: Snapshot, jan_year: int) -> tuple[dict[str, float], str]:
    """Default spread by rating label for a January, and the snapshot key it came from."""
    if jan_year <= SPREAD_HISTORY_LAST_YEAR:
        key = "damodaran/bondspreads.xlsx"
        table = _table(_sheet(snap.read(key), 0), "Rating is")
        column = next((c for c in table.columns
                       if re.fullmatch(rf"Spread:?\s*{jan_year}", c)), None)
        if column is None:
            raise ValueError(f"no spread column for January {jan_year} in {key}")
        spreads = {}
        for _, row in table.iterrows():
            label = str(row["Rating is"]).strip()
            if "/" not in label:
                break  # a second table with finer rating notches follows further down
            if not pd.isna(row[column]):
                spreads[label] = float(row[column])
        return spreads, key
    key = "damodaran/ratings.xls"
    live_year = int(snap.entry(key)["fetched_at"][:4])
    if jan_year != live_year:
        raise ValueError(f"{key} was fetched in {live_year}, it cannot serve January {jan_year}")
    return {label: spread for _, label, spread in load_rating_table(snap)}, key


def load_implied_erp(snap: Snapshot, year: int) -> float:
    """Implied equity risk premium (FCFE) at the end of a year."""
    table = _table(_sheet(snap.read("damodaran/histimpl.xls"), 0), "Year")
    for _, row in table.iterrows():
        try:
            if int(row["Year"]) != year:
                continue
        except (TypeError, ValueError):
            continue
        value = row["Implied ERP (FCFE)"]
        if pd.isna(value):
            break  # the early years have a row but no FCFE-based premium
        return float(value)
    raise ValueError(f"no implied ERP for {year}")


def load_country_premium(snap: Snapshot, country: str, jan_year: int) -> dict[str, float]:
    """Rating-based country risk premium and total equity risk premium for a country."""
    df = _sheet(snap.read(f"damodaran/ctryprem/{jan_year}"), "ERPs by country")
    table = _table(df, "Country")
    row = table[table["Country"].astype(str).str.strip() == country]
    if row.empty:
        raise ValueError(f"{country} is not in the January {jan_year} country premium file")
    first = row.iloc[0]
    # The two premium columns appear twice (rating-based, then CDS-based). Take the first pair.
    names = list(table.columns)
    return {
        "crp": float(first.iloc[names.index("Country Risk Premium")]),
        "total_erp": float(first.iloc[names.index("Total Equity Risk Premium")]),
    }


def load_industry_map(snap: Snapshot) -> dict[str, dict[str, str]]:
    """Industry group by ticker: {'US': {'GOOGL': ...}, 'KR': {'005930': ...}}.

    US covers anything listed on a US exchange, wherever it is incorporated.
    Share classes are written with a dash (BRK-A), as SEC does.
    """
    df = pd.read_excel(io.BytesIO(snap.read("damodaran/indname.xls")), sheet_name="By company name")
    out: dict[str, dict[str, str]] = {"US": {}, "KR": {}, "JP": {}}
    for code, industry in zip(df["Exchange:Ticker"], df["Industry Group"]):
        if not isinstance(code, str) or ":" not in code:
            continue
        exchange, ticker = code.split(":", 1)
        if exchange.startswith(US_EXCHANGE_PREFIXES):
            out["US"][ticker.strip().upper().replace(".", "-")] = str(industry).strip()
        elif exchange in KR_EXCHANGES:
            out["KR"][ticker.strip().lstrip("A")] = str(industry).strip()
        elif exchange == JP_EXCHANGE:
            out["JP"][ticker.strip()] = str(industry).strip()  # the 4-character security code
    return out
