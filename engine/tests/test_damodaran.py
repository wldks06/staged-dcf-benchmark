"""data/damodaran.py: date rules, workbook parsers and fetch fallbacks. No network.

Workbooks are built in memory with openpyxl and stored under the real key names.
pandas sniffs the file format from the bytes, so xlsx bytes under an .xls key load.
The layouts copy the files in snap-2026-10-01-a, cut down to a few rows.
"""

from __future__ import annotations

import io
import math
from datetime import date, datetime

import openpyxl
import pytest

from dcfbench.data import damodaran as dm
from dcfbench.data import snapshot as snapshot_module
from dcfbench.data.http import FetchError
from dcfbench.data.snapshot import Snapshot


def workbook(sheets: dict[str, list[list]]) -> bytes:
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def snap(tmp_path):
    return Snapshot("t", root=tmp_path, readonly=False)


class FakeHttp:
    """Serves bytes for known URLs and fails like data.http.Http for the rest."""

    def __init__(self, pages: dict[str, bytes]):
        self.pages = pages
        self.calls: list[str] = []
        self.requests_made = 0

    def get(self, url, params=None):
        self.calls.append(url)
        self.requests_made += 1
        if url not in self.pages:
            raise FetchError(f"GET {url} failed: HTTP 404")
        return self.pages[url]


# --- which January, which year end ---------------------------------------------------


@pytest.mark.parametrize("day, january, end", [
    (date(2019, 12, 31), 2020, 2019),
    (date(2022, 12, 31), 2023, 2022),
    (date(2025, 12, 31), 2026, 2025),
    (date(2022, 6, 30), 2022, 2021),  # last day that still looks back
    (date(2022, 7, 1), 2023, 2022),  # first day that looks ahead
    (date(2023, 1, 1), 2023, 2022),
    (date(2023, 1, 5), 2023, 2022),
])
def test_january_year_and_year_end_switch_at_mid_year(day, january, end):
    assert dm.january_year(day) == january
    assert dm.year_end(day) == end


@pytest.mark.parametrize("raw, cleaned", [
    ("Industry  Name", "Industry Name"),  # the January 2020 header
    ("Beta ", "Beta"),
    ("  Unlevered beta  corrected for cash ", "Unlevered beta corrected for cash"),
    ("Total\xa0Equity\nRisk Premium", "Total Equity Risk Premium"),
    (2019.0, "2019.0"),
])
def test_clean_collapses_whitespace(raw, cleaned):
    assert dm._clean(raw) == cleaned


# --- industry betas ------------------------------------------------------------------

BETA_HEADER_2020 = ["Industry  Name", "Number of firms", "Beta ", "D/E Ratio", "Effective Tax rate",
                    "Unlevered beta", "Cash/Firm value", "Unlevered beta corrected for cash"]


def beta_sheet(updated, header=BETA_HEADER_2020) -> list[list]:
    return [
        ["Date updated:", updated],
        ["Created by:", "Aswath Damodaran, adamodar@stern.nyu.edu"],
        ["What is this data?", "Beta, Unlevered beta and other risk measures", None, None, None,
         "US companies"],
        [None],
        ["Do you want to use marginal or effective tax rates?", None, None, None, None, "Marginal"],
        list(header),
        ["Advertising", 47, 1.44, 0.85, 0.04, 0.88, 0.06, 0.93],
        [" Software (Entertainment) ", 91, 1.2, 0.1, 0.03, 1.1, 0.02, 1.15],
        ["Total Market", 7053, 1.13, 0.58, 0.07, 0.79, 0.05, 0.83],
        [None],
        ["Notes: betas are regressions against the S&P 500"],
        ["Aggregated", "see notes", "see notes", None, None, "see notes", None, "see notes"],
    ]


def put_betas(snap, jan_year, updated, stem="betas", **kwargs) -> str:
    key = f"damodaran/{stem}/{jan_year}.xls"
    rows = beta_sheet(updated, **kwargs)
    snap.put(key, workbook({"Explanations & FAQ": [["read me"]], "Industry Averages": rows}),
             source="t")
    return key


def test_load_industry_betas_reads_the_2020_layout(snap):
    key = put_betas(snap, 2020, datetime(2020, 1, 5))
    betas = dm.load_industry_betas(snap, 2020)
    assert betas["Advertising"] == dm.IndustryBeta(
        industry="Advertising", unlevered=0.88, unlevered_cash_corrected=0.93, levered=1.44,
        firms=47, date_updated=date(2020, 1, 5), key=key)
    # "Beta " and "Unlevered beta" are different columns and must not be mixed up.
    software = betas["Software (Entertainment)"]
    assert software.levered == 1.2
    assert software.unlevered == 1.1
    assert software.unlevered_cash_corrected == 1.15
    assert isinstance(software.firms, int) and software.firms == 91


def test_load_industry_betas_skips_footer_rows(snap):
    put_betas(snap, 2020, datetime(2020, 1, 5))
    assert sorted(dm.load_industry_betas(snap, 2020)) == [
        "Advertising", "Software (Entertainment)", "Total Market"]


def test_load_industry_betas_reads_the_later_header_spelling(snap):
    header = ["Industry Name", "Number of firms", "Beta ", "D/E Ratio", "Effective Tax rate",
              "Unlevered beta", "Cash/Firm value", "Unlevered beta corrected for cash"]
    put_betas(snap, 2023, datetime(2023, 1, 5), header=header)
    betas = dm.load_industry_betas(snap, 2023)
    assert betas["Advertising"].unlevered == 0.88
    assert betas["Advertising"].date_updated == date(2023, 1, 5)


@pytest.mark.parametrize("region, stem", [("emerging", "betaemerg"), ("global", "betaGlobal")])
def test_load_industry_betas_reads_other_regions_from_their_own_key(snap, region, stem):
    key = put_betas(snap, 2023, datetime(2023, 1, 5), stem=stem)
    assert dm.load_industry_betas(snap, 2023, region=region)["Advertising"].key == key


@pytest.mark.parametrize("file_year", [2019, 2021, 2026])
def test_load_industry_betas_refuses_a_file_of_another_january(snap, file_year):
    # fetch_betas falls back to the live file, which can be a later year than asked for.
    put_betas(snap, 2020, datetime(file_year, 1, 5))
    with pytest.raises(ValueError, match="expected the January 2020 update"):
        dm.load_industry_betas(snap, 2020)


def test_load_industry_betas_refuses_a_file_without_a_date(snap):
    put_betas(snap, 2020, "not a date at all")
    with pytest.raises(ValueError):
        dm.load_industry_betas(snap, 2020)


# --- synthetic rating ----------------------------------------------------------------

RATING_ROWS = [  # lower bound, upper bound, rating, spread: large non-financial firms
    [8.5, 100000, "Aaa/AAA", 0.004],
    [-100000, 0.199999, "D2/D", 0.19],
    [0.2, 2.499999, "B2/B", 0.0321],
    [2.5, 2.999999, "Baa2/BBB", 0.0111],
    [3, 4.249999, "A3/A-", 0.0089],
    [4.25, 8.499999, " A2/A ", 0.0078],
]


def ratings_sheet() -> list[list]:
    financial = [-100000, 0.049999, "D2/D", 0.19]
    return [
        ["Inputs for synthetic rating estimation"],
        ["Enter the type of firm =", None, 2],
        ["Estimated Bond Rating =", None, None, "A2/A"],
        [None],
        ["For large non-financial service firms", None, None, None, None,
         "For financial service firms"],
        ["If interest coverage ratio is", None, None, None, None,
         "If long term interest coverage ratio is"],
        [">", "≤ to", "Rating is", "Spread is", None,
         "greater than", "≤ to", "Rating is", "Spread is"],
        *[row + [None] + financial for row in RATING_ROWS],
        [None],
        ["For smaller and riskier firms"],
        ["If interest coverage ratio is"],
        ["greater than", "≤ to", "Rating is", "Spread is"],
        [-100000, 0.499999, "D2/D", 0.19],
        [12.5, 100000, "Aaa/AAA", 0.004],
    ]


def put_ratings(snap, monkeypatch, fetched_at="2026-10-01T04:06:50Z") -> None:
    monkeypatch.setattr(snapshot_module, "_now", lambda: fetched_at)
    sheets = {"Start here Ratings sheet": ratings_sheet(), "Operating Leases": [["x"]]}
    snap.put("damodaran/ratings.xls", workbook(sheets), source="t")


TABLE = [(-100000.0, "D2/D", 0.19), (0.2, "B2/B", 0.0321), (2.5, "Baa2/BBB", 0.0111),
         (3.0, "A3/A-", 0.0089), (4.25, "A2/A", 0.0078), (8.5, "Aaa/AAA", 0.004)]


def test_load_rating_table_reads_the_large_firm_block_sorted_by_lower_bound(snap, monkeypatch):
    put_ratings(snap, monkeypatch)
    # Six rows: neither the financial-firm columns nor the small-firm block below leak in.
    assert dm.load_rating_table(snap) == TABLE


@pytest.mark.parametrize("coverage, rating", [
    (-1e9, "D2/D"),  # below the lowest bound in the table
    (-100000, "D2/D"),
    (-3.0, "D2/D"),  # an operating loss
    (0.1999, "D2/D"),
    (0.2, "B2/B"),  # exactly on a bound: the higher rating
    (2.4999, "B2/B"),
    (2.5, "Baa2/BBB"),
    (2.6, "Baa2/BBB"),
    (4.2499, "A3/A-"),
    (4.25, "A2/A"),
    (8.4999, "A2/A"),
    (8.5, "Aaa/AAA"),
    (9.0, "Aaa/AAA"),
    (1e9, "Aaa/AAA"),  # above the top of the table
    (math.inf, "Aaa/AAA"),  # no interest expense at all
])
def test_synthetic_rating_at_the_boundaries(coverage, rating):
    assert dm.synthetic_rating(coverage, TABLE) == rating


# --- spreads by rating -----------------------------------------------------------------

SPREAD_ROWS = [
    ["Aaa/AAA", 0.0045, 0.0059, 0.0075, 0.006, 0.004],
    ["A2/A", 0.0085, 0.0107, 0.0138, 0.011, 0.01],
    [" Baa2/BBB ", 0.012, 0.0147, 0.02, 0.016, None],
]


def spread_sheet(extended_table: bool) -> list[list]:
    rows = [
        ["Date updated:", datetime(2024, 1, 5)],
        ["Created by:", "Aswath Damodaran, adamodar@stern.nyu.edu"],
        [None],
        ["Rating is", "Spread 2025", "Spread 2024", "Spread 2019", "Spread: 2017", "Spread: 2015"],
        *SPREAD_ROWS,
    ]
    if extended_table:
        # The real bondspreads24.xlsx carries a second, finer table for the newest year.
        rows += [
            [None],
            ["If you want a more extensive table, here it is"],
            ["Rating is", "Spread 2025"],
            ["AAA", 0.0045],
            ["AA+", 0.0052],
        ]
    return rows


def put_spreads(snap, extended_table=False) -> None:
    sheets = {"Spread data by year": spread_sheet(extended_table)}
    snap.put("damodaran/bondspreads.xlsx", workbook(sheets), source="t")


@pytest.mark.parametrize("jan_year, expected", [
    (2019, {"Aaa/AAA": 0.0075, "A2/A": 0.0138, "Baa2/BBB": 0.02}),  # header "Spread 2019"
    (2017, {"Aaa/AAA": 0.006, "A2/A": 0.011, "Baa2/BBB": 0.016}),  # header "Spread: 2017"
    (2024, {"Aaa/AAA": 0.0059, "A2/A": 0.0107, "Baa2/BBB": 0.0147}),
])
def test_load_spreads_reads_a_past_january_from_the_history_file(snap, jan_year, expected):
    put_spreads(snap, extended_table=True)
    assert dm.load_spreads(snap, jan_year) == (expected, "damodaran/bondspreads.xlsx")


def test_load_spreads_leaves_out_ratings_without_a_spread_that_year(snap):
    put_spreads(snap)
    spreads, _ = dm.load_spreads(snap, 2015)
    assert spreads == {"Aaa/AAA": 0.004, "A2/A": 0.01}


def test_load_spreads_names_a_year_the_history_file_lacks(snap):
    put_spreads(snap)
    with pytest.raises(ValueError, match="no spread column for January 2018"):
        dm.load_spreads(snap, 2018)


def test_load_spreads_routes_the_last_history_year_to_the_history_file(snap):
    # Only the history file is stored, so a wrong turn to ratings.xls would fail.
    put_spreads(snap)
    assert dm.SPREAD_HISTORY_LAST_YEAR == 2025
    spreads, key = dm.load_spreads(snap, dm.SPREAD_HISTORY_LAST_YEAR)
    assert key == "damodaran/bondspreads.xlsx"
    assert spreads == {"Aaa/AAA": 0.0045, "A2/A": 0.0085, "Baa2/BBB": 0.012}


def test_load_spreads_reads_2025_from_the_real_layout(snap):
    put_spreads(snap, extended_table=True)
    spreads, key = dm.load_spreads(snap, 2025)
    assert key == "damodaran/bondspreads.xlsx"
    assert "Rating is" not in spreads
    assert {label: spreads[label] for label in ("Aaa/AAA", "A2/A", "Baa2/BBB")} == {
        "Aaa/AAA": 0.0045, "A2/A": 0.0085, "Baa2/BBB": 0.012}


def test_load_spreads_takes_a_later_january_from_the_live_rating_file(snap, monkeypatch):
    put_ratings(snap, monkeypatch, fetched_at="2026-10-01T04:06:50Z")
    spreads, key = dm.load_spreads(snap, 2026)
    assert key == "damodaran/ratings.xls"
    assert spreads == {label: spread for _, label, spread in TABLE}


@pytest.mark.parametrize("fetched_at, jan_year", [
    ("2026-10-01T04:06:50Z", 2027),
    ("2027-02-01T00:00:00Z", 2026),
])
def test_load_spreads_refuses_the_live_file_of_another_year(snap, monkeypatch, fetched_at,
                                                           jan_year):
    put_ratings(snap, monkeypatch, fetched_at=fetched_at)
    with pytest.raises(ValueError, match=f"cannot serve January {jan_year}"):
        dm.load_spreads(snap, jan_year)


# --- implied equity risk premium ---------------------------------------------------------

HISTIMPL = [
    ["Date updated:", datetime(2026, 1, 5)],
    ["What is this data?", "Implied Equity Risk Premiums", None, None, None, "S&P 500"],
    [None],
    ["Year", "Earnings Yield", "T.Bond Rate", "Implied Premium (DDM)", "Implied ERP (FCFE)",
     "Implied Premium (FCFE with sustainable Payout)"],
    [1960, 0.0534, 0.0276, None, None, None],
    [1961, 0.0471, 0.0235, 0.0292, 0.0292, None],
    [2019, 0.0504, 0.0192, 0.0196, 0.052, 0.0399],
    [2022.0, 0.0572, 0.0388, 0.0216, 0.0594, 0.0511],
    ["2025", 0.0397, 0.0418, 0.0169, 0.0423, 0.0418],
    [None],
    ["* Earnings and dividends are for the trailing twelve months"],
    [None, "Period", "ERP"],
    [None, "1960-2025", 0.0425],
]


@pytest.fixture
def histimpl(snap):
    sheets = {"Historical Impl Premiums": HISTIMPL, "Sheet2": [["x"]]}
    snap.put("damodaran/histimpl.xls", workbook(sheets), source="t")
    return snap


@pytest.mark.parametrize("year, erp", [
    (2019, 0.052), (2022, 0.0594), (2025, 0.0423), (1961, 0.0292)])
def test_load_implied_erp_reads_the_fcfe_column_of_the_year_row(histimpl, year, erp):
    # Not the DDM premium next to it, and not the footnote and summary rows below.
    assert dm.load_implied_erp(histimpl, year) == erp


def test_load_implied_erp_of_a_year_not_in_the_file_is_an_error(histimpl):
    with pytest.raises(ValueError, match="no implied ERP for 2021"):
        dm.load_implied_erp(histimpl, 2021)


def test_load_implied_erp_of_a_year_with_an_empty_cell_is_an_error(histimpl):
    with pytest.raises(ValueError):
        dm.load_implied_erp(histimpl, 1960)


# --- country risk premium ----------------------------------------------------------------

# The CDS-based pair repeats the names of the rating-based pair. The real files
# (ctryprem19.xlsx, ctryprem22.xlsx, ctryprem.xlsx) number the repeats, older ones may not.
CDS_HEADERS = {
    "numbered": ["Total Equity Risk Premium2", "Country Risk Premium3"],
    "repeated": ["Total Equity Risk Premium", "Country Risk Premium"],
}


def ctryprem_sheet(cds_headers: list[str]) -> list[list]:
    return [
        ["Country and Equity Risk Premiums"],
        ["Date of update:", datetime(2023, 1, 5)],
        ["Enter the current risk premium for a mature equity market", None, None, None, 0.046],
        [None],
        ["Country", "Africa", "Moody's rating", "Rating-based Default Spread",
         "Total Equity Risk Premium", "Country Risk Premium", "Sovereign CDS, net of US",
         *cds_headers, "Has to be sorted in ascending order"],
        ["Abu Dhabi", "Middle East", "Aa2", 0.0049, 0.0529, 0.0069, 0.0036, 0.0511, 0.0051, "Aaa"],
        ["Korea ", "Asia", "Aa2", 0.0049, 0.0529, 0.0069, 0.0025, 0.0495, 0.0035, "A1"],
        ["United States", "North America", "Aaa", 0, 0.046, 0, 0, 0.046, 0, "A2"],
        ["Argentina", "South America", "Ca", 0.12, 0.215, 0.169, None, None, None, "A3"],
    ]


@pytest.fixture(params=sorted(CDS_HEADERS))
def ctryprem(snap, request):
    rows = ctryprem_sheet(CDS_HEADERS[request.param])
    sheets = {"Explanation and FAQ": [["x"]], "Country Lookup": [["x"]], "ERPs by country": rows}
    snap.put("damodaran/ctryprem/2023", workbook(sheets), source="t")
    return snap


def test_load_country_premium_takes_the_first_of_the_duplicated_columns(ctryprem):
    # Rating-based 0.0069 and 0.0529, not the CDS-based 0.0035 and 0.0495 further right.
    expected = {
        "Korea": {"crp": 0.0069, "total_erp": 0.0529},
        "United States": {"crp": 0.0, "total_erp": 0.046},
        "Argentina": {"crp": 0.169, "total_erp": 0.215},
    }
    for country, premium in expected.items():
        assert dm.load_country_premium(ctryprem, country, 2023) == premium


def test_load_country_premium_of_an_unknown_country_is_an_error(ctryprem):
    with pytest.raises(ValueError, match="Atlantis is not in the January 2023"):
        dm.load_country_premium(ctryprem, "Atlantis", 2023)


# --- industry map --------------------------------------------------------------------------

def company(name, code, industry, country) -> list:
    return [name, code, industry, "a sector", 1000, country]


INDNAME = [
    ["Company Name", "Exchange:Ticker", "Industry Group", "Primary Sector", "SIC Code", "Country"],
    company("Alphabet Inc.", "NasdaqGS:GOOGL", "Software (Entertainment)", "United States"),
    company("Johnson & Johnson", "NYSE:JNJ", "Drugs (Pharmaceutical)", "United States"),
    company("Berkshire Hathaway Inc.", "NYSE:BRK.A", "Diversified", "United States"),
    company("Alibaba Group", "NYSE:BABA", "Retail (General)", "China"),
    # Stray spaces and a lower-case ticker, to see them cleaned up.
    company("Small cap", "NasdaqCM:smll ", " Oil/Gas (Production and Exploration) ", "Canada"),
    company("Mid cap", "NasdaqGM:MIDD", "Machinery", "United States"),
    company("Amex name", "NYSEAM:AMX", "Precious Metals", "Canada"),
    company("Cboe listed", "BATS:CBOE", "Brokerage & Investment Banking", "United States"),
    company("Meta Corporation PCL", "SET:META", "Engineering/Construction", "Thailand"),
    company("Pink sheet name", "OTCPK:PINK", "Entertainment", "United States"),
    company("Toyota Motor", "TSE:7203", "Auto & Truck", "Japan"),
    company("Samsung Electronics", "KOSE:A005930", "Computers/Peripherals", "South Korea"),
    company("09WOMEN", "KOSDAQ:A366030", "Retail (Special Lines)", "South Korea"),
    company("New style code", "KOSDAQ:A0007C0", "Machinery", "South Korea"),
    company("Delisted, no ticker", None, "Metals & Mining", "New Zealand"),
    company("Placeholder ticker", "-", "Metals & Mining", "New Zealand"),
]


@pytest.fixture
def industry_map(snap):
    sheets = {"By industry": [["x"]], "By company name": INDNAME, "By geography": [["x"]]}
    snap.put("damodaran/indname.xls", workbook(sheets), source="t")
    return dm.load_industry_map(snap)


def test_industry_map_groups_us_exchanges_wherever_the_company_is_incorporated(industry_map):
    assert industry_map["US"] == {
        "GOOGL": "Software (Entertainment)",
        "JNJ": "Drugs (Pharmaceutical)",
        "BRK-A": "Diversified",
        "BABA": "Retail (General)",  # a Chinese company on the NYSE
        "SMLL": "Oil/Gas (Production and Exploration)",
        "MIDD": "Machinery",
        "AMX": "Precious Metals",
        "CBOE": "Brokerage & Investment Banking",
    }


def test_industry_map_writes_share_classes_with_a_dash(industry_map):
    assert "BRK-A" in industry_map["US"]
    assert "BRK.A" not in industry_map["US"]


def test_industry_map_strips_the_leading_a_from_korean_codes(industry_map):
    assert industry_map["KR"] == {
        "005930": "Computers/Peripherals",
        "366030": "Retail (Special Lines)",
        "0007C0": "Machinery",  # codes issued since 2024 carry a letter
    }


def test_industry_map_ignores_other_exchanges_and_rows_without_a_ticker(industry_map):
    # SET:META must not shadow or join NasdaqGS:META, and OTC names are not "US listed".
    for ticker in ("META", "PINK", "7203", "-"):
        assert ticker not in industry_map["US"]
        assert ticker not in industry_map["KR"]
    assert set(industry_map) == {"US", "KR", "JP"}
    # a Tokyo listing goes to the Japanese map under its security code, when the fixture has one
    assert all(len(code) == 4 for code in industry_map["JP"])


# --- fetch ------------------------------------------------------------------------------------


@pytest.mark.parametrize("jan_year, yy", [(2023, "22"), (2020, "19"), (2010, "09"), (2001, "00")])
def test_fetch_betas_asks_for_the_archive_numbered_one_year_back(snap, jan_year, yy):
    archive = f"{dm.BASE}/archives/betas{yy}.xls"
    http = FakeHttp({archive: b"archived", f"{dm.BASE}/datasets/betas.xls": b"live"})
    dm.fetch_betas(snap, http, jan_year)
    assert http.calls == [archive]
    assert snap.read(f"damodaran/betas/{jan_year}.xls") == b"archived"
    assert snap.entry(f"damodaran/betas/{jan_year}.xls")["source"] == archive


def test_fetch_betas_falls_back_to_the_live_file_for_the_newest_january(snap):
    live = f"{dm.BASE}/datasets/betas.xls"
    http = FakeHttp({live: b"live"})
    dm.fetch_betas(snap, http, 2026)
    assert http.calls == [f"{dm.BASE}/archives/betas25.xls", live]
    assert snap.read("damodaran/betas/2026.xls") == b"live"
    assert snap.entry("damodaran/betas/2026.xls")["source"] == live


@pytest.mark.parametrize("region, stem", [("emerging", "betaemerg"), ("global", "betaGlobal")])
def test_fetch_betas_uses_the_file_stem_of_the_region(snap, region, stem):
    archive = f"{dm.BASE}/archives/{stem}22.xls"
    dm.fetch_betas(snap, FakeHttp({archive: b"regional"}), 2023, region=region)
    assert snap.keys() == [f"damodaran/{stem}/2023.xls"]


def test_fetch_betas_raises_when_no_url_works_and_stores_nothing(snap):
    http = FakeHttp({})
    with pytest.raises(FetchError, match="datasets/betas.xls"):
        dm.fetch_betas(snap, http, 2023)
    assert http.requests_made == 2
    assert snap.keys() == []


def test_fetch_betas_does_nothing_when_the_file_is_stored(snap):
    snap.put("damodaran/betas/2023.xls", b"stored", source="t")
    http = FakeHttp({})
    dm.fetch_betas(snap, http, 2023)
    assert http.requests_made == 0


def test_fetch_country_premiums_tries_both_archive_extensions_then_the_live_file(snap):
    live = f"{dm.BASE}/datasets/ctryprem.xlsx"
    http = FakeHttp({live: b"live"})
    dm.fetch_country_premiums(snap, http, 2023)
    assert http.calls == [
        f"{dm.BASE}/archives/ctryprem22.xlsx", f"{dm.BASE}/archives/ctryprem22.xls", live]
    assert snap.read("damodaran/ctryprem/2023") == b"live"

    older = FakeHttp({f"{dm.BASE}/archives/ctryprem19.xls": b"old format"})
    dm.fetch_country_premiums(snap, older, 2020)
    assert snap.read("damodaran/ctryprem/2020") == b"old format"
    assert older.requests_made == 2


def test_fetch_common_stores_the_four_shared_files(snap):
    pages = {
        f"{dm.BASE}/archives/bondspreads24.xlsx": b"spreads",
        f"{dm.BASE}/ratings.xls": b"ratings",
        f"{dm.BASE}/datasets/histimpl.xls": b"erp",
        f"{dm.BASE}/datasets/indname.xls": b"industries",
    }
    http = FakeHttp(pages)
    dm.fetch_common(snap, http)
    assert {key: snap.read(key) for key in snap.keys()} == {
        "damodaran/bondspreads.xlsx": b"spreads",
        "damodaran/ratings.xls": b"ratings",
        "damodaran/histimpl.xls": b"erp",
        "damodaran/indname.xls": b"industries",
    }
    # A second run finds everything in the snapshot.
    dm.fetch_common(snap, http)
    assert http.requests_made == 4
