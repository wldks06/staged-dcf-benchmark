"""data/fred.py: parsing both stored shapes, date lookups, and the API or CSV choice.

No network. fetch_series asks config.secret for FRED_API_KEY, and secret reads the
repo .env on first use, so every fetch test switches that off first.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from dcfbench import config
from dcfbench.data import fred
from dcfbench.data.snapshot import Snapshot, SnapshotError

KEY = "TESTKEY-0123456789abcdef"

# The keyless download: a header, then one row per day, holidays left empty.
CSV = (b"observation_date,DGS10\n"
       b"2022-12-28,3.88\n"
       b"2022-12-29,3.83\n"
       b"2022-12-30,3.88\n"
       b"2023-01-02,\n"
       b"2023-01-03,3.79\n"
       b"2023-01-04,.\n"
       b"2023-01-05,3.72\n")

# The API: values are strings and a missing day is a dot.
API_JSON = {
    "realtime_start": "2026-10-01", "realtime_end": "2026-10-01", "count": 5,
    "observations": [
        {"realtime_start": "2026-10-01", "realtime_end": "2026-10-01",
         "date": "2022-12-29", "value": "3.83"},
        {"date": "2022-12-30", "value": "3.88"},
        {"date": "2023-01-02", "value": "."},
        {"date": "2023-01-03", "value": 3.79},
        {"date": "2023-01-04", "value": ""},
    ],
}


class FakeHttp:
    def __init__(self, content: bytes):
        self.content = content
        self.calls: list[tuple[str, dict | None]] = []
        self.requests_made = 0

    def get(self, url, params=None):
        self.calls.append((url, params))
        self.requests_made += 1
        return self.content


@pytest.fixture
def snap(tmp_path):
    return Snapshot("t", root=tmp_path, readonly=False)


@pytest.fixture
def dotenv_off(monkeypatch):
    """Mark the .env as already loaded, so the real file cannot leak a key in."""
    monkeypatch.setattr(config, "_loaded", True)


# --- load_series ------------------------------------------------------------------


def test_load_series_parses_the_keyless_csv(snap):
    snap.put("fred/DGS10.csv", CSV, source="t")
    assert fred.load_series(snap, "DGS10") == [
        (date(2022, 12, 28), 3.88), (date(2022, 12, 29), 3.83), (date(2022, 12, 30), 3.88),
        (date(2023, 1, 3), 3.79), (date(2023, 1, 5), 3.72),
    ]


def test_load_series_csv_tolerates_crlf_and_blank_lines(snap):
    snap.put("fred/DTB3.csv", b"observation_date,DTB3\r\n2022-12-30,4.30\r\n\r\n", source="t")
    assert fred.load_series(snap, "DTB3") == [(date(2022, 12, 30), 4.30)]


def test_load_series_parses_the_api_json(snap):
    snap.put("fred/DGS10.json", json.dumps(API_JSON).encode("utf-8"), source="t")
    assert fred.load_series(snap, "DGS10") == [
        (date(2022, 12, 29), 3.83), (date(2022, 12, 30), 3.88), (date(2023, 1, 3), 3.79),
    ]


def test_load_series_of_an_unknown_series_is_an_error(snap):
    with pytest.raises(SnapshotError, match="fred/NOPE.csv is not in snapshot"):
        fred.load_series(snap, "NOPE")


# --- value_on_or_before -------------------------------------------------------------

SERIES = [(date(2022, 12, 28), 3.88), (date(2022, 12, 29), 3.83), (date(2022, 12, 30), 3.88),
          (date(2023, 1, 3), 3.79)]


def test_value_on_or_before_picks_the_last_observation_on_or_before_the_day():
    assert fred.value_on_or_before(SERIES, date(2022, 12, 29)) == (date(2022, 12, 29), 3.83)
    assert fred.value_on_or_before(SERIES, date(2022, 12, 31)) == (date(2022, 12, 30), 3.88)
    assert fred.value_on_or_before(SERIES, date(2023, 1, 2)) == (date(2022, 12, 30), 3.88)
    assert fred.value_on_or_before(SERIES, date(2023, 1, 3)) == (date(2023, 1, 3), 3.79)
    assert fred.value_on_or_before(SERIES, date(2023, 1, 10)) == (date(2023, 1, 3), 3.79)


def test_value_on_or_before_is_none_before_the_first_observation():
    assert fred.value_on_or_before(SERIES, date(2022, 12, 27)) is None
    assert fred.value_on_or_before([], date(2022, 12, 27)) is None


@pytest.mark.parametrize("frequency, limit", [("D", 10), ("M", 45), ("Q", 135)])
def test_value_on_or_before_respects_the_age_limit_of_the_frequency(frequency, limit):
    observed = date(2022, 1, 1)
    series = [(observed, 1.5)]
    assert fred.MAX_AGE_DAYS[frequency] == limit
    on_the_limit = observed + timedelta(days=limit)
    assert fred.value_on_or_before(series, on_the_limit, frequency=frequency) == (observed, 1.5)
    assert fred.value_on_or_before(series, on_the_limit + timedelta(days=1),
                                   frequency=frequency) is None


def test_value_on_or_before_defaults_to_the_daily_limit():
    series = [(date(2022, 12, 1), 250.0)]
    assert fred.value_on_or_before(series, date(2022, 12, 31)) is None
    assert fred.value_on_or_before(series, date(2022, 12, 31), frequency="M") == series[0]


def test_a_series_that_starts_late_cannot_serve_an_early_date():
    # FRED keeps three years of the ICE BofA spreads, so the first row is October 2023.
    oas = [(date(2023, 10, 2), 1.08), (date(2023, 10, 3), 1.11)]
    assert fred.value_on_or_before(oas, date(2022, 12, 31)) is None
    assert fred.value_on_or_before(oas, date(2023, 10, 2)) == (date(2023, 10, 2), 1.08)


# --- fetch_series --------------------------------------------------------------------


def test_fetch_series_uses_the_api_when_a_key_is_set(snap, monkeypatch, dotenv_off):
    monkeypatch.setenv("FRED_API_KEY", KEY)
    http = FakeHttp(json.dumps(API_JSON).encode("utf-8"))
    fred.fetch_series(snap, http, "DGS10")
    assert http.calls == [
        (fred.API_URL, {"series_id": "DGS10", "api_key": KEY, "file_type": "json"})]
    assert snap.keys() == ["fred/DGS10.json"]
    # The key went out with the request but is not written down.
    assert snap.entry("fred/DGS10.json")["source"] == (
        f"{fred.API_URL}?series_id=DGS10&api_key=REDACTED&file_type=json")
    assert len(fred.load_series(snap, "DGS10")) == 3


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_fetch_series_uses_the_keyless_csv_without_a_key(snap, monkeypatch, dotenv_off, value):
    if value is None:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
    else:
        monkeypatch.setenv("FRED_API_KEY", value)
    http = FakeHttp(CSV)
    fred.fetch_series(snap, http, "DGS10")
    assert http.calls == [(fred.CSV_URL, {"id": "DGS10"})]
    assert snap.keys() == ["fred/DGS10.csv"]
    assert snap.entry("fred/DGS10.csv")["source"] == f"{fred.CSV_URL}?id=DGS10"
    assert len(fred.load_series(snap, "DGS10")) == 5


def test_fetch_series_finds_the_key_in_the_env_file(snap, monkeypatch, tmp_path):
    # Set then delete, so monkeypatch puts back whatever load_env writes into os.environ.
    monkeypatch.setenv("FRED_API_KEY", "placeholder")
    monkeypatch.delenv("FRED_API_KEY")
    monkeypatch.setattr(config, "_loaded", False)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    (tmp_path / ".env").write_text(f"FRED_API_KEY={KEY}\n", encoding="utf-8")
    http = FakeHttp(json.dumps(API_JSON).encode("utf-8"))
    fred.fetch_series(snap, http, "DTB3")
    assert http.calls[0][1]["api_key"] == KEY
    assert snap.keys() == ["fred/DTB3.json"]
    assert KEY not in json.dumps(snap._manifest)


@pytest.mark.parametrize("suffix", ["json", "csv"])
@pytest.mark.parametrize("key_set", [True, False], ids=["with-key", "without-key"])
def test_fetch_series_does_nothing_when_the_series_is_stored(snap, monkeypatch, dotenv_off,
                                                             suffix, key_set):
    if key_set:
        monkeypatch.setenv("FRED_API_KEY", KEY)
    else:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
    snap.put(f"fred/DGS10.{suffix}", b"stored earlier", source="t")
    http = FakeHttp(b"fresh")
    fred.fetch_series(snap, http, "DGS10")
    assert http.requests_made == 0
    assert snap.keys() == [f"fred/DGS10.{suffix}"]
    assert snap.read(f"fred/DGS10.{suffix}") == b"stored earlier"


# --- the series lists ----------------------------------------------------------------


def test_series_lists_match_the_plan():
    assert set(fred.US_SERIES) == {"DTB3", "DGS10", "DGS20", "DGS30", "DFII10", "T10YIE",
                                   "CPIAUCSL", "GDP", "GDPC1", "SOFR"}
    assert fred.OAS_SERIES == {
        "AAA": "BAMLC0A1CAAA", "AA": "BAMLC0A2CAA", "A": "BAMLC0A3CA", "BBB": "BAMLC0A4CBBB",
        "BB": "BAMLH0A1HYBB", "B": "BAMLH0A2HYB", "CCC": "BAMLH0A3HYC",
    }
