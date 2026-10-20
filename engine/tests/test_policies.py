"""Policy block defaults: textbook, practitioner and trap policies."""

from datetime import date

import pytest
from pydantic import ValidationError

from conftest import synthetic_inputs
from dcfbench.engine import trap_answers, value_case
from dcfbench.policies import (
    KR_PRACTITIONER, KR_TEXTBOOK, PRACTITIONER, TEXTBOOK, policy_warnings,
    statutory_tax_rate, trap_policy,
)
from dcfbench.schema import Case, Company, PolicyBlock, make_case_id

# Textbook policy. g is a decimal here.
SECTION_5_TEXTBOOK = dict(
    cash_flow="FCFF", tax_on_ebit="statutory", sbc_treatment="expense",
    lease_treatment="capitalize", nwc_definition="balance_sheet", timing="year_end",
    horizon=5, growth_source="history_cagr", reinvestment_rule="tied", rf_source="DTB3",
    erp_source="rwj_7", beta_source="damodaran_industry", beta_adjustment="raw",
    relever="hamada", rd_method="rf_plus_spread", tax_shield_rate="statutory",
    weights="market", rate_structure="firm_wide", hurdle_premium_pp=0, tv_method="gordon",
    g=0.02, terminal_cleanup="on", cash_treatment="all_excess", share_count="diluted",
    as_of_rule="filed_on_or_before_date", market="US", accounting_standard="US_GAAP",
    currency="USD", country_premium_rule="none",
)
# Fields where the practitioner column differs from the textbook column.
SECTION_5_PRACTITIONER_DIFF = dict(
    tax_on_ebit="effective", timing="mid_year", rf_source="DGS10", erp_source="kroll_5_0",
    beta_adjustment="blume", g=0.025, cash_treatment="operating_pct",
)


def diff(a: PolicyBlock, b: PolicyBlock) -> dict:
    da, db = a.model_dump(), b.model_dump()
    return {k: db[k] for k in da if da[k] != db[k]}


def test_textbook_defaults_match_section_5():
    dumped = TEXTBOOK.model_dump()
    for field, value in SECTION_5_TEXTBOOK.items():
        assert dumped[field] == value, field


def test_practitioner_differs_only_where_section_5_says():
    assert diff(TEXTBOOK, PRACTITIONER) == SECTION_5_PRACTITIONER_DIFF


@pytest.mark.parametrize("trap, changed, warning", [
    ("T1", {"erp_source": "kroll_5_0"}, "rf_erp_mismatch"),
    ("T2", {"weights": "book"}, "book_weights"),
    ("T3", {"rd_method": "coupon"}, "historical_cost_of_debt"),
    ("T5", {"cash_flow": "FCFE"}, "fcfe_at_wacc"),
    ("T6", {"sbc_treatment": "add_back", "share_count": "basic"}, "sbc_addback_no_dilution"),
])
def test_traps_change_only_their_fields(trap, changed, warning):
    policy = trap_policy(trap)
    assert diff(TEXTBOOK, policy) == changed
    assert policy_warnings(policy) == [warning]


def test_named_policies_are_consistent():
    for policy in (TEXTBOOK, PRACTITIONER, KR_TEXTBOOK, KR_PRACTITIONER):
        assert policy_warnings(policy) == []


def test_us_default_on_a_korean_case_is_flagged():
    policy = PolicyBlock(market="KR", currency="KRW", accounting_standard="K_IFRS")
    assert "rf_market_mismatch" in policy_warnings(policy)


def test_t4_sets_g_below_wacc():
    assert trap_policy("T4", wacc=0.08).g == pytest.approx(0.0775)
    with pytest.raises(ValueError):
        trap_policy("T4")


def test_unknown_field_or_value_is_rejected():
    with pytest.raises(ValidationError):
        PolicyBlock(rf_sourse="DGS10")
    with pytest.raises(ValidationError):
        PolicyBlock(rf_source="LIBOR")
    with pytest.raises(ValidationError):
        PolicyBlock(hurdle_premium_pp=7)


@pytest.mark.parametrize("market, day, rate", [
    ("US", date(2019, 12, 31), 0.21),
    ("US", date(2025, 12, 31), 0.21),
    ("US", date(2016, 12, 31), 0.35),
    ("KR", date(2019, 12, 31), 0.275),
    ("KR", date(2022, 12, 31), 0.264),  # the cut for 2023 was enacted in December 2022
    ("KR", date(2025, 12, 31), 0.275),
])
def test_statutory_tax_rate(market, day, rate):
    assert statutory_tax_rate(market, day) == rate


def test_case_round_trips_through_json():
    inputs = synthetic_inputs()
    day = date(2022, 12, 31)
    case = Case(
        case_id=make_case_id("US", "TEST", day, "textbook"),
        company=Company(ticker="TEST", name="Test Co", cik="0000000001", fye_month=12),
        valuation_date=day,
        policy=TEXTBOOK,
        policy_label="textbook",
        snapshot_id="snap-test",
        inputs=inputs,
        checkpoints=value_case(inputs, TEXTBOOK, day),
        trap_answers=trap_answers(inputs, day),
    )
    assert case.case_id == "US-TEST-2022-12-31-textbook"
    assert Case.model_validate_json(case.model_dump_json()) == case
