from datetime import date

import pytest

from dcfbench.schema import Inputs

VALUATION_DATE = date(2022, 12, 31)


def synthetic_inputs(**overrides) -> Inputs:
    """A made-up firm with round ratios: 10 percent growth, 20 percent margin."""
    data = dict(
        fiscal_years=["2020", "2021", "2022"],
        revenue=[1000.0, 1100.0, 1210.0],
        ebit=[200.0, 220.0, 242.0],
        da=[50.0, 55.0, 60.5],
        capex=[60.0, 66.0, 72.6],
        nwc=[100.0, 110.0, 121.0],
        tax_expense=[36.0, 44.0, 54.45],
        pretax_income=[180.0, 200.0, 217.8],
        interest_expense=[20.0, 20.0, 24.2],
        sbc=[10.0, 11.0, 12.1],
        cash=150.0,
        st_investments=50.0,
        debt_total=400.0,
        lease_liability=100.0,
        preferred=0.0,
        minority_interest=20.0,
        book_equity=800.0,
        shares_basic=100.0,
        shares_diluted=104.0,
        price=30.0,
        market_cap=3000.0,
        rates={"DTB3": 0.04, "DGS10": 0.045, "DGS20": 0.048, "oas_rating": 0.012},
        beta_unlevered_industry=0.9,
        rating="A",
    )
    data.update(overrides)
    return Inputs(**data)


@pytest.fixture
def inputs() -> Inputs:
    return synthetic_inputs()


@pytest.fixture
def valuation_date() -> date:
    return VALUATION_DATE
