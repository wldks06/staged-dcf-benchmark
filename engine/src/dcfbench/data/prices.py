"""Share prices from Yahoo Finance through yfinance.

Unofficial source: fetched once into the snapshot and never called during runs.

Yahoo's Close is adjusted for later stock splits. A valuation as of a past date
needs the price that actually traded, so the stored series is un-adjusted with the
split history: raw close = Close times every split ratio dated after that day.
The same split history brings share counts from an older filing onto the share
basis of the valuation date.

Yahoo also records spin-offs as "splits" with odd ratios (AT&T 1.324 in 2022,
Honeywell 1.061 in 2025). They rescale past prices, so they count when a price is
un-adjusted, but a spin-off does not change the number of shares, so they are left
out when a share count is rebased.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

from .snapshot import Snapshot

HISTORY_START = "2018-01-01"
MAX_AGE_DAYS = 10
WHOLE_SPLIT_TOLERANCE = 0.002  # Yahoo lists Alphabet's 2014 two-for-one as 1.998


class AmbiguousCorporateAction(ValueError):
    """A ratio below one that is not a clean reverse split.

    Yahoo folds a reverse split and a spin-off on the same day into one number (DuPont,
    June 2019: 1 for 3 and the Corteva spin-off give 0.4725). The effect on the share
    count cannot be read off such a ratio.
    """


def is_share_split(ratio: float) -> bool:
    """True for a real split (2, 20, 1.5, 0.125), false for a spin-off ratio such as 1.324.

    A split is a whole number of new shares per old share, a whole number of old shares
    per new share, or an exact simple fraction (3 for 2, 5 for 4). Spin-off ratios come
    out of a price calculation and land on such a value only by accident.
    """
    for value in (ratio, 1 / ratio):
        whole = round(value)
        if whole >= 2 and abs(value - whole) <= WHOLE_SPLIT_TOLERANCE * value:
            return True
    return any(abs(ratio - p / q) < 1e-6
               for q in (2, 3, 4, 5, 10) for p in range(1, 101) if p % q)


def fetch_prices(snap: Snapshot, symbol: str) -> bool:
    """Store daily closes and splits for a Yahoo symbol. False if Yahoo has no data."""
    key = f"prices/{symbol}.json"
    if snap.has(key):
        return True
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    history = ticker.history(start=HISTORY_START, auto_adjust=False, actions=True)
    if history.empty:
        return False
    try:
        currency = ticker.fast_info["currency"]
    except Exception:
        currency = None
    payload = {
        "symbol": symbol,
        "currency": currency,
        "library": f"yfinance {yf.__version__}",
        "note": "close is split-adjusted as delivered by Yahoo, not dividend-adjusted",
        "closes": [[ts.date().isoformat(), round(float(c), 6)]
                   for ts, c in history["Close"].items() if c == c],
        # Full split history, not only the window, so old share counts can be rebased.
        "splits": [[ts.date().isoformat(), float(r)] for ts, r in ticker.splits.items() if r > 0],
    }
    snap.put(key, json.dumps(payload).encode("utf-8"), source=f"yfinance:{symbol}")
    return True


@dataclass(frozen=True)
class PriceHistory:
    symbol: str
    currency: str | None
    closes: list[tuple[date, float]]
    splits: list[tuple[date, float]]

    def split_factor(self, after: date, upto: date) -> float:
        """Product of split ratios with after < split date <= upto."""
        factor = 1.0
        for day, ratio in self.splits:
            if after < day <= upto:
                factor *= ratio
        return factor

    def share_split_factor(self, after: date, upto: date) -> float:
        """Like split_factor, but only for events that change the number of shares.

        Raises AmbiguousCorporateAction when the window holds a ratio below one that is
        not a clean reverse split.
        """
        factor = 1.0
        for day, ratio in self.splits:
            if not after < day <= upto:
                continue
            if is_share_split(ratio):
                factor *= ratio
            elif ratio < 1:
                raise AmbiguousCorporateAction(f"{self.symbol} {day}: ratio {ratio}")
        return factor

    def raw_close(self, day: date) -> tuple[date, float] | None:
        """The close that actually traded on the last session on or before day."""
        best = None
        for obs_date, close in self.closes:
            if obs_date > day:
                break
            best = (obs_date, close)
        if best is None or day - best[0] > timedelta(days=MAX_AGE_DAYS):
            return None
        later_splits = self.split_factor(best[0], date.max)
        return best[0], best[1] * later_splits


def load_prices(snap: Snapshot, symbol: str) -> PriceHistory:
    raw = snap.read_json(f"prices/{symbol}.json")
    return PriceHistory(
        raw["symbol"], raw.get("currency"),
        [(date.fromisoformat(d), c) for d, c in raw["closes"]],
        [(date.fromisoformat(d), r) for d, r in raw["splits"]],
    )
