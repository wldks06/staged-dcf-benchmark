"""Guide example and its sensitivity grid."""

import pytest

from dcfbench.engine import dcf, equity_bridge, gordon_tv, sensitivity_grid
from dcfbench.errors import ValuationError

FLOWS = [100, 105, 110, 116, 122]
R = 0.09
G = 0.025
NET_DEBT = 300
SHARES = 100


def test_year_end():
    result = dcf(FLOWS, R, g=G)
    assert round(result.pv_flows, 1) == 426.5
    assert round(result.tv, 1) == 1923.8
    assert round(result.pv_tv, 1) == 1250.4
    assert round(result.ev, 1) == 1676.9
    equity = equity_bridge(result.ev, debt=NET_DEBT)
    assert round(equity, 1) == 1376.9
    assert round(equity / SHARES, 2) == 13.77


def test_mid_year():
    year_end = dcf(FLOWS, R, g=G)
    mid_year = dcf(FLOWS, R, g=G, shift=0.5)
    assert round(mid_year.ev, 1) == 1750.7
    assert round(mid_year.ev / year_end.ev - 1, 3) == 0.044
    # With a Gordon terminal value the whole stream moves half a year closer.
    assert mid_year.ev == pytest.approx(year_end.ev * (1 + R) ** 0.5)


def test_sensitivity_grid():
    grid = sensitivity_grid(FLOWS, [0.08, 0.09, 0.10, 0.11], [0.020, 0.025, 0.030])
    assert [[round(v) for v in row] for row in grid] == [
        [1850, 1986, 2149],
        [1582, 1677, 1788],
        [1381, 1451, 1530],
        [1225, 1278, 1337],
    ]


def test_growth_at_or_above_rate_is_refused():
    with pytest.raises(ValuationError):
        gordon_tv(122, 0.09, 0.09)
    grid = sensitivity_grid(FLOWS, [0.03, 0.09], [0.03])
    assert grid[0][0] is None and grid[1][0] is not None


def test_given_terminal_value_is_discounted_from_year_end():
    # An exit-multiple terminal value is a value at the end of year n, whatever the flow timing.
    tv = 2000.0
    result = dcf(FLOWS, R, tv=tv, shift=0.5)
    assert result.pv_tv == pytest.approx(tv / (1 + R) ** 5)
