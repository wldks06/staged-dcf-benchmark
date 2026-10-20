"""data/prices.py: split handling and price lookups. yfinance is never called.

fetch_prices is exercised with a stub module in place of yfinance, so the payload
shape checked here is the one the function itself writes.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import date

import pandas as pd
import pytest

from dcfbench.data.prices import (
    HISTORY_START,
    MAX_AGE_DAYS,
    PriceHistory,
    fetch_prices,
    is_share_split,
    load_prices,
)
from dcfbench.data.snapshot import Snapshot


def history(closes, splits=()) -> PriceHistory:
    return PriceHistory(
        "TEST", "USD",
        [(date.fromisoformat(d), c) for d, c in closes],
        [(date.fromisoformat(d), r) for d, r in splits],
    )


# Alphabet around its 20-for-1 split. Closes are split-adjusted, as Yahoo delivers them.
ALPHABET = history(
    closes=[("2019-12-31", 66.9695), ("2022-07-15", 111.7775), ("2022-07-18", 109.03),
            ("2022-12-30", 88.23), ("2023-01-03", 89.12)],
    splits=[("2014-04-03", 1.998), ("2022-07-18", 20.0)],
)


@pytest.fixture
def snap(tmp_path):
    return Snapshot("t", root=tmp_path, readonly=False)


# --- split_factor ---------------------------------------------------------------


def test_split_factor_window_is_open_at_the_start_and_closed_at_the_end():
    split_day, before, after = date(2022, 7, 18), date(2022, 7, 17), date(2022, 7, 19)
    assert ALPHABET.split_factor(before, split_day) == 20.0  # upto is included
    assert ALPHABET.split_factor(split_day, after) == 1.0  # after is excluded
    assert ALPHABET.split_factor(before, before) == 1.0
    assert ALPHABET.split_factor(before, after) == 20.0


def test_split_factor_ignores_splits_outside_the_window():
    assert ALPHABET.split_factor(date(2019, 12, 31), date(2022, 12, 31)) == 20.0
    assert ALPHABET.split_factor(date(2022, 12, 31), date(2025, 12, 31)) == 1.0
    assert ALPHABET.split_factor(date(2010, 1, 1), date(2019, 12, 31)) == 1.998


def test_several_splits_multiply():
    tesla = history([], splits=[("2020-08-31", 5.0), ("2022-08-25", 3.0)])
    assert tesla.split_factor(date(2019, 12, 31), date(2022, 12, 31)) == 15.0
    assert tesla.split_factor(date(2021, 2, 8), date(2022, 12, 31)) == 3.0


def test_split_factor_is_one_without_splits():
    assert history([]).split_factor(date(2019, 12, 31), date(2022, 12, 31)) == 1.0


# --- spin-offs that Yahoo lists as splits ---------------------------------------


@pytest.mark.parametrize("ratio", [2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 20.0, 25.0, 1.998])
def test_whole_number_ratios_are_share_splits(ratio):
    assert is_share_split(ratio)


@pytest.mark.parametrize("ratio", [1.5, 2.5, 1.25, 1.2, 0.5, 0.25, 0.2, 0.1, 1 / 3])
def test_simple_fractions_are_share_splits(ratio):
    assert is_share_split(ratio)


# Ratios Yahoo reports for spin-offs of S&P 100 companies, all seen in the snapshot.
SPIN_OFF_RATIOS = [1.324, 1.061, 1.011, 1.032, 1.04, 1.487, 1.589, 1.054, 1.048, 1.046, 1.402,
                   1.281, 1.128, 1.196, 1.253, 2.39, 1.067, 1.241, 1.122, 2.084201750729471]


@pytest.mark.parametrize("ratio", SPIN_OFF_RATIOS)
def test_spin_off_ratios_are_not_share_splits(ratio):
    assert not is_share_split(ratio)


@pytest.mark.parametrize("ratio", [0.125, 0.05, 1 / 6],
                         ids=["GE 1-for-8 in 2021", "AIG 1-for-20 in 2009", "BKNG 1-for-6 in 2003"])
def test_reverse_splits_are_share_splits(ratio):
    assert is_share_split(ratio)


def test_share_split_factor_leaves_spin_offs_out():
    att = history([], splits=[("2022-04-11", 1.324)])
    assert att.share_split_factor(date(2022, 2, 16), date(2022, 12, 31)) == 1.0
    assert att.split_factor(date(2022, 2, 16), date(2022, 12, 31)) == 1.324
    mixed = history([], splits=[("2020-08-31", 4.0), ("2021-06-03", 1.048), ("2022-08-25", 3.0)])
    assert mixed.share_split_factor(date(2019, 12, 31), date(2022, 12, 31)) == 12.0
    assert mixed.split_factor(date(2019, 12, 31), date(2022, 12, 31)) == pytest.approx(12.576)


def test_share_split_factor_uses_the_same_window_as_split_factor():
    split_day, before, after = date(2022, 7, 18), date(2022, 7, 17), date(2022, 7, 19)
    assert ALPHABET.share_split_factor(before, split_day) == 20.0
    assert ALPHABET.share_split_factor(split_day, after) == 1.0
    # Yahoo's 1.998 for the 2014 two-for-one still counts as a split.
    assert ALPHABET.share_split_factor(date(2010, 1, 1), date(2022, 12, 31)) == pytest.approx(39.96)


# --- raw_close --------------------------------------------------------------------


def test_raw_close_picks_the_last_session_on_or_before_the_day():
    assert ALPHABET.raw_close(date(2022, 12, 31)) == (date(2022, 12, 30), 88.23)  # a Saturday
    assert ALPHABET.raw_close(date(2022, 12, 30)) == (date(2022, 12, 30), 88.23)
    assert ALPHABET.raw_close(date(2023, 1, 3)) == (date(2023, 1, 3), 89.12)


def test_raw_close_undoes_only_splits_dated_after_the_price_date():
    day, price = ALPHABET.raw_close(date(2019, 12, 31))
    assert day == date(2019, 12, 31)
    assert price == pytest.approx(1339.39)  # 66.9695 * 20, the 2014 split is long past
    assert ALPHABET.raw_close(date(2022, 7, 15))[1] == pytest.approx(2235.55)
    # The close on the split date already trades on the new basis.
    assert ALPHABET.raw_close(date(2022, 7, 18)) == (date(2022, 7, 18), 109.03)


def test_raw_close_undoes_every_later_split():
    tesla = history([("2019-12-31", 27.888666)], splits=[("2020-08-31", 5.0), ("2022-08-25", 3.0)])
    assert tesla.raw_close(date(2019, 12, 31))[1] == pytest.approx(418.33)


def test_raw_close_undoes_spin_off_ratios_too():
    # Yahoo rescales past prices for a spin-off, so the traded price needs it back.
    att = history([("2019-12-31", 29.516616)], splits=[("2022-04-11", 1.324)])
    assert att.raw_close(date(2019, 12, 31))[1] == pytest.approx(39.08)


def test_raw_close_is_none_when_the_last_price_is_too_old():
    stale = history([("2022-12-20", 50.0)])
    assert MAX_AGE_DAYS == 10
    assert stale.raw_close(date(2022, 12, 30)) == (date(2022, 12, 20), 50.0)  # exactly 10 days
    assert stale.raw_close(date(2022, 12, 31)) is None  # 11 days


def test_raw_close_is_none_when_there_is_no_earlier_price():
    assert ALPHABET.raw_close(date(2019, 12, 30)) is None
    assert history([]).raw_close(date(2022, 12, 31)) is None


# --- fetch_prices and load_prices -------------------------------------------------


def payload(symbol="TEST", currency="USD") -> dict:
    """The shape fetch_prices stores."""
    return {
        "symbol": symbol,
        "currency": currency,
        "library": "yfinance 0.0-test",
        "note": "close is split-adjusted as delivered by Yahoo, not dividend-adjusted",
        "closes": [["2022-07-15", 111.7775], ["2022-07-18", 109.03]],
        "splits": [["2014-04-03", 1.998], ["2022-07-18", 20.0]],
    }


def test_load_prices_round_trips_a_stored_payload(snap):
    snap.put("prices/TEST.json", json.dumps(payload()).encode("utf-8"), source="yfinance:TEST")
    loaded = load_prices(snap, "TEST")
    assert loaded == PriceHistory(
        "TEST", "USD",
        [(date(2022, 7, 15), 111.7775), (date(2022, 7, 18), 109.03)],
        [(date(2014, 4, 3), 1.998), (date(2022, 7, 18), 20.0)],
    )
    assert loaded.raw_close(date(2022, 7, 17))[1] == pytest.approx(2235.55)


def test_load_prices_accepts_a_missing_currency(snap):
    raw = payload(currency=None)
    snap.put("prices/TEST.json", json.dumps(raw).encode("utf-8"), source="t")
    assert load_prices(snap, "TEST").currency is None
    del raw["currency"]
    snap.put("prices/OLD.json", json.dumps(raw).encode("utf-8"), source="t")
    assert load_prices(snap, "OLD").currency is None


def install_fake_yfinance(monkeypatch, frame, splits, currency="USD") -> dict:
    calls: dict = {}

    class FakeTicker:
        def __init__(self, symbol):
            calls["symbol"] = symbol
            self.splits = splits
            self.fast_info = {"currency": currency} if currency else {}

        def history(self, **kwargs):
            calls["history"] = kwargs
            return frame

    fake = types.SimpleNamespace(Ticker=FakeTicker, __version__="0.0-test")
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    return calls


def new_york(days) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(days, tz="America/New_York")


def test_fetch_prices_stores_closes_and_the_full_split_history(snap, monkeypatch):
    frame = pd.DataFrame({"Close": [111.7775, float("nan"), 109.0312345678]},
                         index=new_york(["2022-07-15", "2022-07-16", "2022-07-18"]))
    splits = pd.Series([1.998, 20.0, 0.0],
                       index=new_york(["2014-04-03", "2022-07-18", "2023-01-02"]))
    calls = install_fake_yfinance(monkeypatch, frame, splits)

    assert fetch_prices(snap, "TEST") is True
    assert calls == {"symbol": "TEST",
                     "history": {"start": HISTORY_START, "auto_adjust": False, "actions": True}}
    stored = snap.read_json("prices/TEST.json")
    assert stored["symbol"] == "TEST"
    assert stored["currency"] == "USD"
    assert stored["library"] == "yfinance 0.0-test"
    # The day without a price is dropped and closes are rounded to six places.
    assert stored["closes"] == [["2022-07-15", 111.7775], ["2022-07-18", 109.031235]]
    assert stored["splits"] == [["2014-04-03", 1.998], ["2022-07-18", 20.0]]
    assert snap.entry("prices/TEST.json")["source"] == "yfinance:TEST"

    loaded = load_prices(snap, "TEST")
    assert loaded.closes == [(date(2022, 7, 15), 111.7775), (date(2022, 7, 18), 109.031235)]
    assert loaded.splits == [(date(2014, 4, 3), 1.998), (date(2022, 7, 18), 20.0)]


def test_fetch_prices_tolerates_a_missing_currency(snap, monkeypatch):
    frame = pd.DataFrame({"Close": [10.0]}, index=new_york(["2022-07-15"]))
    install_fake_yfinance(monkeypatch, frame, pd.Series([], dtype=float), currency=None)
    assert fetch_prices(snap, "TEST") is True
    assert snap.read_json("prices/TEST.json")["currency"] is None
    assert load_prices(snap, "TEST").splits == []


def test_fetch_prices_returns_false_when_yahoo_has_no_data(snap, monkeypatch):
    install_fake_yfinance(monkeypatch, pd.DataFrame({"Close": []}), pd.Series([], dtype=float))
    assert fetch_prices(snap, "GONE") is False
    assert not snap.has("prices/GONE.json")


def test_fetch_prices_does_nothing_when_the_symbol_is_stored(snap, monkeypatch):
    snap.put("prices/TEST.json", json.dumps(payload()).encode("utf-8"), source="yfinance:TEST")
    # None in sys.modules makes any import of yfinance fail loudly.
    monkeypatch.setitem(sys.modules, "yfinance", None)
    assert fetch_prices(snap, "TEST") is True
