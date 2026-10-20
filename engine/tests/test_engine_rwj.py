"""RWJ Feline Fancy (RWJ 12.6).

Every assertion compares against the published number rounded to the cent.
"""

from dcfbench.engine import dcf, equity_bridge
from dcfbench.forecast import fcff

WACC = 0.08
TAX = 0.21
DEBT = 40.0
SHARES = 3.5
GROWTH = 0.15  # years 2 to 5
G = 0.02  # after year 5


def feline_fancy_flows() -> list[float]:
    scale = [(1 + GROWTH) ** t for t in range(5)]
    return [fcff(ebit=10.00 * k, tax_rate=TAX, da=1.50 * k, capex=2.40 * k, dnwc=0.80 * k)
            for k in scale]


def test_cfa_star_by_year():
    assert [round(f, 2) for f in feline_fancy_flows()] == [6.20, 7.13, 8.20, 9.43, 10.84]


def test_gordon_terminal_value_and_firm_value():
    result = dcf(feline_fancy_flows(), WACC, g=G)
    assert round(result.tv, 2) == 184.35
    assert round(result.ev, 2) == 158.14


def test_equity_and_price():
    result = dcf(feline_fancy_flows(), WACC, g=G)
    equity = equity_bridge(result.ev, debt=DEBT)
    assert round(equity, 2) == 118.14
    assert round(equity / SHARES, 2) == 33.75


def test_price_sales_terminal_value():
    sales_year5 = 30 * (1 + GROWTH) ** 4
    assert round(sales_year5, 2) == 52.47
    tv = 3 * sales_year5
    assert round(tv, 2) == 157.41
    result = dcf(feline_fancy_flows(), WACC, tv=tv)
    assert round(result.ev, 2) == 139.80
    assert round(equity_bridge(result.ev, debt=DEBT) / SHARES, 2) == 28.52
