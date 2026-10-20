"""EDGAR resolver: as-of filter, period matching, tag fallbacks."""

from datetime import date

import pytest

from dcfbench.data import edgar
from dcfbench.data.edgar import FactStore, resolve_company
from dcfbench.data.snapshot import Snapshot

AS_OF = date(2022, 12, 31)
YEARS = (2016, 2017, 2018, 2019, 2020, 2021)  # the window as of 2022-12-31 is 2019 to 2021


def duration(year, value, *, filed=None, form="10-K", fp="FY", accn=None, start=None, end=None):
    return {
        "start": start or f"{year}-01-01", "end": end or f"{year}-12-31", "val": value,
        "accn": accn or f"0000000001-{(year + 1) % 100:02d}-000001", "fy": year, "fp": fp,
        "form": form, "filed": filed or f"{year + 1}-02-15",
    }


def instant(year, value, *, filed=None, form="10-K", fp="FY", accn=None, end=None):
    row = duration(year, value, filed=filed, form=form, fp=fp, accn=accn, end=end)
    del row["start"]
    return row


def base_tags() -> dict:
    """A company that resolves every required input with first-choice tags."""
    flows = {
        "Revenues": 1000, "OperatingIncomeLoss": 200, "InterestExpense": 20,
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": 180,
        "IncomeTaxExpenseBenefit": 36, "DepreciationDepletionAndAmortization": 50,
        "PaymentsToAcquirePropertyPlantAndEquipment": 60, "ShareBasedCompensation": 10,
    }
    balances = {
        "AccountsReceivableNetCurrent": 150, "InventoryNet": 80, "AccountsPayableCurrent": 90,
        "CashAndCashEquivalentsAtCarryingValue": 120, "LongTermDebtNoncurrent": 300,
        "LongTermDebtCurrent": 40, "StockholdersEquity": 500, "Liabilities": 700,
    }
    tags = {tag: {"USD": [duration(y, v + y - 2018) for y in YEARS]} for tag, v in flows.items()}
    tags.update({tag: {"USD": [instant(y, v + y - 2018) for y in YEARS]}
                 for tag, v in balances.items()})
    tags["WeightedAverageNumberOfDilutedSharesOutstanding"] = {
        "shares": [duration(y, 104e6) for y in YEARS]}
    return tags


def store_from(tags: dict, cover_shares: float | None = 100e6) -> FactStore:
    facts = {"us-gaap": {tag: {"units": units} for tag, units in tags.items()}}
    if cover_shares is not None:
        facts["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            instant(y, cover_shares, end=f"{y + 1}-01-31") for y in YEARS]}}}
    return FactStore({"cik": 1, "entityName": "Test Co", "facts": facts})


def resolved(tags=None, as_of=AS_OF, **kwargs):
    return resolve_company(store_from(tags if tags is not None else base_tags(), **kwargs), as_of)


def values(ci, name):
    return [r.value for r in ci.series[name]]


def test_base_company_resolves_cleanly():
    ci = resolved()
    assert ci.issues == []
    # The log holds the assumed zeros and the debt recipe, which is rarely the first one.
    assert sorted(ci.fallbacks) == [
        "debt_total:2021:fallback_3:LongTermDebtNoncurrent + LongTermDebtCurrent",
        "lease_liability:2021:tag_absent_assumed_zero",
        "minority_interest:2021:tag_absent_assumed_zero",
        "preferred:2021:tag_absent_assumed_zero",
        "st_investments:2021:tag_absent_assumed_zero",
    ]
    assert [e.year for e in ci.fiscal_year_ends] == [2019, 2020, 2021]
    assert values(ci, "revenue") == [1001, 1002, 1003]
    assert ci.scalars["debt_total"].value == 303 + 43
    assert ci.scalars["shares_basic"].value == 100e6
    assert ci.scalars["shares_diluted"].value == 104e6
    assert ci.prior_nwc["receivables"].value == 150  # the year before the window


def test_as_of_hides_later_filings():
    # As of 2021-06-30 the FY2021 report does not exist: the window slides back a year.
    ci = resolved(as_of=date(2021, 6, 30))
    assert [e.year for e in ci.fiscal_year_ends] == [2018, 2019, 2020]
    for items in (r.provenance for r in ci.series["revenue"]):
        assert all(p.filed <= date(2021, 6, 30) for p in items)


def test_restatement_is_used_only_once_it_is_filed():
    tags = base_tags()
    # The FY2021 report (filed 2022-02-15) restates FY2020 revenue from 1002 to 950.
    tags["Revenues"]["USD"].append(
        duration(2020, 950, filed="2022-02-15", accn="0000000001-22-000001"))
    before = resolved(tags, as_of=date(2021, 12, 31))
    assert values(before, "revenue")[-1] == 1002
    after = resolved(tags, as_of=AS_OF)
    assert values(after, "revenue")[1] == 950
    notes = [p.note for p in after.series["revenue"][1].provenance]
    assert "superseded by a later filing" in notes


def test_period_is_matched_by_dates_not_by_fy():
    tags = base_tags()
    for row in tags["Revenues"]["USD"]:
        row["fy"] = 2021  # comparatives carry the fiscal year of the filing they sit in
    assert values(resolved(tags), "revenue") == [1001, 1002, 1003]


def test_annual_facts_labelled_q4_are_accepted():
    tags = base_tags()
    for units in tags.values():
        for rows in units.values():
            for row in rows:
                row["fp"] = "Q4"
    assert resolved(tags).issues == []


def test_quarterly_and_10q_facts_are_ignored():
    tags = base_tags()
    tags["Revenues"]["USD"] += [
        duration(2021, 260, start="2021-10-01"),  # fourth quarter inside the 10-K
        duration(2021, 9999, form="10-Q", fp="Q3", filed="2022-03-01"),  # wrong form
    ]
    assert values(resolved(tags), "revenue")[-1] == 1003


def test_revenue_fallback_is_logged():
    tags = base_tags()
    tags["RevenueFromContractWithCustomerExcludingAssessedTax"] = tags.pop("Revenues")
    ci = resolved(tags)
    assert ci.issues == [] and values(ci, "revenue") == [1001, 1002, 1003]
    assert sum(f.startswith("revenue:") and "fallback_1" in f for f in ci.fallbacks) == 3


def test_one_recipe_for_the_whole_window_when_it_covers_it():
    tags = base_tags()
    # The first-choice tag exists only for the last year, the second covers all three.
    tags["RevenueFromContractWithCustomerExcludingAssessedTax"] = {
        "USD": [duration(y, 900) for y in YEARS]}
    tags["Revenues"]["USD"] = [duration(2021, 1003)]
    ci = resolved(tags)
    assert values(ci, "revenue") == [900, 900, 900]
    assert not any("mixed_tags" in f for f in ci.fallbacks)


def test_mixed_tags_across_the_window_are_logged():
    tags = base_tags()
    tags["RevenueFromContractWithCustomerExcludingAssessedTax"] = {
        "USD": [duration(2019, 900), duration(2020, 901)]}
    tags["Revenues"]["USD"] = [duration(2021, 1003)]
    ci = resolved(tags)
    assert values(ci, "revenue") == [900, 901, 1003]
    assert "revenue:window:mixed_tags_across_years" in ci.fallbacks


def test_ebit_falls_back_to_pretax_plus_interest():
    tags = base_tags()
    del tags["OperatingIncomeLoss"]
    ci = resolved(tags)
    assert values(ci, "ebit") == [181 + 21, 182 + 22, 183 + 23]
    assert any(f.startswith("ebit:2021:fallback_1:@pretax_income + @interest_expense")
               for f in ci.fallbacks)


def test_da_takes_the_largest_candidate_total():
    tags = base_tags()
    # A broad tag carrying a small sub-item must not shadow the real total (Intel, McDonald's).
    tags["Depreciation"] = {"USD": [duration(y, 70) for y in YEARS]}
    tags["AmortizationOfIntangibleAssets"] = {"USD": [duration(y, 15) for y in YEARS]}
    ci = resolved(tags)
    assert values(ci, "da") == [85, 85, 85]
    assert any("Depreciation + AmortizationOfIntangibleAssets" in f for f in ci.fallbacks)


@pytest.mark.parametrize("debt_tags, expected", [
    ({"LongTermDebtNoncurrent": 300, "DebtCurrent": 70, "LongTermDebtCurrent": 40}, 370),
    ({"LongTermDebtAndCapitalLeaseObligations": 300, "DebtCurrent": 70}, 370),
    ({"LongTermDebtNoncurrent": 300, "LongTermDebtCurrent": 40, "ShortTermBorrowings": 25,
      "CommercialPaper": 20}, 365),
    ({"LongTermDebtNoncurrent": 300}, 300),
    ({"LongTermDebt": 340, "CommercialPaper": 20}, 360),
    ({"NotesPayableCurrent": 55}, 55),
    ({"DebtLongtermAndShorttermCombinedAmount": 410, "LongTermDebtNoncurrent": 300}, 410),
])
def test_debt_recipes_do_not_double_count(debt_tags, expected):
    tags = base_tags()
    del tags["LongTermDebtNoncurrent"], tags["LongTermDebtCurrent"]
    for tag, value in debt_tags.items():
        tags[tag] = {"USD": [instant(y, value) for y in YEARS]}
    assert resolved(tags).scalars["debt_total"].value == expected


def drop_debt(tags):
    del tags["LongTermDebtNoncurrent"], tags["LongTermDebtCurrent"]
    return tags


def test_no_borrowing_tags_and_no_interest_means_no_debt():
    tags = drop_debt(base_tags())
    del tags["InterestExpense"]
    ci = resolved(tags)
    assert ci.issues == []
    assert ci.scalars["debt_total"].value == 0 and values(ci, "interest_expense") == [0, 0, 0]
    assert "debt_total:2021:no_borrowing_tags_assumed_zero" in ci.fallbacks


def test_negligible_interest_without_borrowing_tags_means_no_debt():
    tags = drop_debt(base_tags())
    tags["InterestExpense"] = {"USD": [duration(y, 1) for y in YEARS]}  # 0.5 percent of EBIT
    ci = resolved(tags)
    assert ci.issues == [] and ci.scalars["debt_total"].value == 0
    assert values(ci, "interest_expense") == [1, 1, 1]


def test_material_interest_without_borrowing_tags_is_a_gap():
    ci = resolved(drop_debt(base_tags()))
    assert ci.issues == ["missing_debt_total:2021"]


def test_debt_free_company_without_operating_income_still_gets_ebit():
    tags = drop_debt(base_tags())
    del tags["InterestExpense"], tags["OperatingIncomeLoss"]
    ci = resolved(tags)
    assert ci.issues == [] and values(ci, "ebit") == [181, 182, 183]


def test_absent_optional_inputs():
    tags = base_tags()
    del tags["InventoryNet"], tags["ShareBasedCompensation"], tags["StockholdersEquity"]
    ci = resolved(tags)
    assert ci.issues == []
    assert values(ci, "inventory") == [0, 0, 0]
    assert ci.series["inventory"][0].note == "tag_absent_assumed_zero"
    assert values(ci, "sbc") == [None, None, None]
    assert ci.scalars["book_equity"].value is None


def test_lease_liability_note_depends_on_asc842():
    before = resolved(as_of=date(2019, 12, 31))  # last year end 2018-12-31
    assert before.scalars["lease_liability"].note == "pre_asc842_assumed_zero"
    after = resolved()
    assert after.scalars["lease_liability"].note == "tag_absent_assumed_zero"
    tags = base_tags()
    tags["OperatingLeaseLiabilityNoncurrent"] = {"USD": [instant(y, 30) for y in YEARS]}
    tags["OperatingLeaseLiabilityCurrent"] = {"USD": [instant(y, 5) for y in YEARS]}
    assert resolved(tags).scalars["lease_liability"].value == 35


def test_missing_required_input_is_an_issue_with_its_year():
    tags = base_tags()
    tags["PaymentsToAcquirePropertyPlantAndEquipment"]["USD"] = [
        r for r in tags["PaymentsToAcquirePropertyPlantAndEquipment"]["USD"] if r["fy"] != 2020]
    assert resolved(tags).issues == ["missing_capex:2020"]


def test_shares_basic_fallbacks():
    tags = base_tags()
    tags["CommonStockSharesOutstanding"] = {"shares": [instant(y, 98e6) for y in YEARS]}
    tags["WeightedAverageNumberOfSharesOutstandingBasic"] = {
        "shares": [duration(y, 99e6) for y in YEARS]}
    assert resolved(tags).scalars["shares_basic"].value == 100e6  # cover page first
    balance_sheet = resolved(tags, cover_shares=None)
    assert balance_sheet.scalars["shares_basic"].value == 98e6
    assert "shares_basic:2021:fallback_1:CommonStockSharesOutstanding" in balance_sheet.fallbacks
    del tags["CommonStockSharesOutstanding"]
    assert resolved(tags, cover_shares=None).scalars["shares_basic"].value == 99e6
    del tags["WeightedAverageNumberOfSharesOutstandingBasic"]
    assert resolved(tags, cover_shares=None).issues == ["missing_shares_basic:2021"]


def test_diluted_shares_from_eps_when_only_classes_are_tagged():
    tags = base_tags()
    del tags["WeightedAverageNumberOfDilutedSharesOutstanding"]
    assert resolved(tags).issues == ["missing_shares_diluted:2021"]
    tags["NetIncomeLoss"] = {"USD": [duration(y, 520e6) for y in YEARS]}
    tags["EarningsPerShareDiluted"] = {"USD/shares": [duration(y, 5.0) for y in YEARS]}
    ci = resolved(tags)
    assert ci.issues == [] and ci.scalars["shares_diluted"].value == 104e6
    assert any("NetIncomeLoss / EarningsPerShareDiluted" in f for f in ci.fallbacks)


def test_too_few_fiscal_years():
    tags = base_tags()
    for units in tags.values():
        for unit, rows in units.items():
            units[unit] = [r for r in rows if r["fy"] >= 2020]
    assert resolved(tags).issues == ["only_2_fiscal_years"]


def test_fifty_two_week_years_form_a_chain():
    ends = {2019: "2019-12-28", 2020: "2021-01-02", 2021: "2022-01-01"}
    starts = {2019: "2018-12-30", 2020: "2019-12-29", 2021: "2021-01-03"}
    tags = {"Revenues": {"USD": [
        duration(y, 1000, start=starts[y], end=ends[y], filed=f"{y + 1}-02-20") for y in ends]}}
    store = store_from(tags, cover_shares=None)
    chain = store.fiscal_year_ends(AS_OF, 3)
    assert chain == [date(2022, 1, 1), date(2021, 1, 2), date(2019, 12, 28)]
    assert [edgar.fiscal_year_label(e) for e in chain] == ["2021", "2020", "2019"]


def test_ticker_and_cik_formats():
    assert edgar.normalize_ticker(" brk.b ") == "BRK-B"
    assert edgar.pad_cik(320193) == "0000320193" and edgar.pad_cik("0000320193") == "0000320193"


def test_load_filings_as_of(tmp_path):
    submissions = {"filings": {"recent": {
        "accessionNumber": ["a-3", "a-2", "a-1", "a-0"],
        "filingDate": ["2023-02-15", "2022-10-28", "2022-02-15", "2022-01-05"],
        "reportDate": ["2022-12-31", "2022-09-30", "2021-12-31", ""],
        "form": ["10-K", "10-Q", "10-K", "8-K"],
        "primaryDocument": ["k22.htm", "q3.htm", "k21.htm", "8k.htm"],
    }, "files": []}}
    import json
    with Snapshot("t", root=tmp_path, readonly=False) as snap:
        snap.put("edgar/submissions/CIK0000000001.json", json.dumps(submissions).encode(),
                 source="test")
        filings = edgar.load_filings(snap, "1", AS_OF)
    assert [f.accn for f in filings] == ["a-2", "a-1"]  # newest first, 8-K and later 10-K left out
    assert filings[0].report_date == date(2022, 9, 30)
