"""FRED series.

With FRED_API_KEY the official API is used. Without it the keyless CSV download
of the same series is used, which is enough for version zero. Both store the
full history, and lookups take the last observation on or before a date.

Note on credit spreads: since 2026 FRED carries only three years of history for
the ICE BofA option-adjusted spreads, so they cannot serve valuation dates before
October 2023. Version zero takes the spread by rating from Damodaran's January
tables instead (damodaran.py) and keeps the FRED series as a cross-check.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta

from ..config import secret
from .http import Http
from .snapshot import Snapshot

API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

US_SERIES = ("DTB3", "DGS10", "DGS20", "DGS30", "DFII10", "T10YIE", "CPIAUCSL", "GDP", "GDPC1",
             "SOFR")
OAS_SERIES = {
    "AAA": "BAMLC0A1CAAA", "AA": "BAMLC0A2CAA", "A": "BAMLC0A3CA", "BBB": "BAMLC0A4CBBB",
    "BB": "BAMLH0A1HYBB", "B": "BAMLH0A2HYB", "CCC": "BAMLH0A3HYC",
}
# Korean rates carried by FRED (OECD, monthly averages). ECOS has the daily series.
KR_SERIES = {"KTB10Y": "IRLTLT01KRM156N", "CD91": "IR3TIB01KRM156N"}
# Japanese rates carried by FRED (OECD, monthly averages). The Ministry of Finance has the daily curve.
JP_SERIES = {"JGB10Y": "IRLTLT01JPM156N", "JPY3M": "IR3TIB01JPM156N"}

# Longest acceptable gap between the lookup date and the observation used.
MAX_AGE_DAYS = {"D": 10, "M": 45, "Q": 135}


def fred_http() -> Http:
    return Http(min_interval=0.6)


def fetch_series(snap: Snapshot, http: Http, series_id: str) -> None:
    if snap.has(f"fred/{series_id}.json") or snap.has(f"fred/{series_id}.csv"):
        return
    api_key = secret("FRED_API_KEY", required=False)
    if api_key:
        snap.fetch(f"fred/{series_id}.json", API_URL, http,
                   params={"series_id": series_id, "api_key": api_key, "file_type": "json"})
    else:
        snap.fetch(f"fred/{series_id}.csv", CSV_URL, http, params={"id": series_id})


def load_series(snap: Snapshot, series_id: str) -> list[tuple[date, float]]:
    """Observations oldest first, missing values dropped. Values are in FRED's units."""
    out: list[tuple[date, float]] = []
    if snap.has(f"fred/{series_id}.json"):
        for row in snap.read_json(f"fred/{series_id}.json")["observations"]:
            if row["value"] not in (".", ""):
                out.append((date.fromisoformat(row["date"]), float(row["value"])))
    else:
        text = snap.read(f"fred/{series_id}.csv").decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        next(reader)  # header: observation_date,SERIES
        for row in reader:
            if len(row) >= 2 and row[1] not in (".", ""):
                out.append((date.fromisoformat(row[0]), float(row[1])))
    return out


def value_on_or_before(series: list[tuple[date, float]], day: date, *,
                       frequency: str = "D") -> tuple[date, float] | None:
    """The last observation dated on or before day, or None if there is none recent enough."""
    best = None
    for obs_date, value in series:
        if obs_date > day:
            break
        best = (obs_date, value)
    if best is None or day - best[0] > timedelta(days=MAX_AGE_DAYS[frequency]):
        return None
    return best
