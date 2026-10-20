"""Build the 2019, 2022 and held-out 2025 question sets from the engine's cases.

    python build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../data/questions/QA_set_v2.json \
        --dates 2019-12-31,2022-12-31 --out ../data/questions/QA_set_ver03.json
    python build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../data/questions/QA_set_v2.json \
        --dates 2025-12-31 --new-companies --out ../data/questions/QA_set_ver03_newco.json

Why: QA_set_v2 (the main set, 184 evaluated questions) holds one valuation date, 2025-12-31. Holding the
companies fixed and moving the date isolates the rate environment (in 2019 the 3-month bill was 1.5%, in
2025 3.6%); the held-out set adds five companies that are not in v2 (paper, Section IV-A).

What is generated per company-date (same numbering as v2):
  <TICKER>-<YEAR>-05  Level 3 Full DCF, textbook policy      tier "basic@<YEAR>"
  <TICKER>-<YEAR>-06  Level 4 Half DCF A (Steps 2-3)         tier "half@<YEAR>"
  <TICKER>-<YEAR>-07  Level 5 Half DCF B (Steps 4-5)         tier "half@<YEAR>"
  <TICKER>-<YEAR>-08  Level 3 Full DCF, practitioner policy  tier "complex@<YEAR>"

Differences from v2, on purpose:
- Level 3 prints EVERY figure in the question ("Figures (use these as stated)") instead of splitting
  them between "taken from the 10-K" and "figures given". For v2 the runner appends the figures that the
  question text leaves out (run_model.py, data_table), so the information a model sees is the same.
  Because the figures are in the text, the L3 rubric has no "input" items (v2 has them, but the
  grader skips them at Level 3), so total points are lower than v2's for the same question type.
- Every Level 3 and Level 5 question carries the 0-point basic-share "alternative" item.
Everything else (assumption wording, report line, rubric items, points, tolerances) follows v2, and the
builder reproduces all 40 v2 half-DCF questions word for word when pointed at 2025.
Every target is the dcf-bench case checkpoint AND is re-checked against the independent engine
(dcf_independent.py); the build stops if they differ.
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcf_independent import value_case  # noqa: E402

M = 1e6


def money(v):            # $ millions, one decimal, thousands separators
    return f"{v / M:,.1f}"


def pct(x, nd=2):
    return f"{x * 100:.{nd}f}%"


def three(vals):
    return ", ".join(f"${money(v)}" for v in vals)


DEFAULT_TAGS = {"ebit": {"OperatingIncomeLoss"}, "da": {"DepreciationDepletionAndAmortization"},
                "capex": {"PaymentsToAcquirePropertyPlantAndEquipment"}, "receivables": {"AccountsReceivableNetCurrent"},
                "inventory": {"InventoryNet"}, "payables": {"AccountsPayableCurrent"},
                "cash": {"CashAndCashEquivalentsAtCarryingValue"}, "st_investments": {"ShortTermInvestments"},
                "lease_liability": {"OperatingLeaseLiability"}, "preferred": {"PreferredStockValue"},
                "minority_interest": {"MinorityInterest"}}


def zero_note(case, key):
    """v2's '(case definition: ...)' note, rule learned from v2 (reproduces all 40 v2 L4/L5 texts):
    one recipe per fiscal year (that year's tags joined by ' + '; 'not tagged in the filing, taken as zero'
    for a zero-filled year; 'pretax income plus interest expense' for a derived EBIT); recipes that are just
    the usual tag are dropped; the rest, sorted, are joined by '; '. No note when nothing is left."""
    p = case["inputs"]["provenance"].get(key)
    plist = [x for x in (p if isinstance(p, list) else [p]) if isinstance(x, dict)]
    by_year = {}
    for x in plist:
        by_year.setdefault(x.get("fiscal_year") or "", []).append(x)
    recipes = set()
    for yr, xs in by_year.items():
        if all(x.get("note") == "tag_absent_assumed_zero" for x in xs):
            recipes.add("not tagged in the filing, taken as zero")
            continue
        tags = []
        for x in xs:
            t = (x.get("tag") or "").split(":")[-1]
            if t and t not in tags:
                tags.append(t)
        if key == "ebit" and any("BeforeIncomeTaxes" in t for t in tags):
            recipes.add("pretax income plus interest expense")
        elif tags and not (key == "revenue" or set(tags) <= DEFAULT_TAGS.get(key, set())):
            recipes.add(" + ".join(tags))
    return f" (case definition: {'; '.join(sorted(recipes))})" if recipes else ""


def debt_note(case):
    p = case["inputs"]["provenance"].get("debt_total") or []
    tags = [x.get("tag", "").split(":")[-1] for x in (p if isinstance(p, list) else [p]) if isinstance(x, dict) and x.get("tag")]
    return f" (case definition: {' + '.join(tags)})" if tags else ""


ASSUMPTIONS_1_7 = """Assumptions:
1. Horizon: 5 forecast years after FY{fy}.
2. Revenue growth: year-1 growth is the compound annual growth rate of revenue from FY{fy0} to FY{fy} (two growth periods), held between 0% and 15%. Growth then falls in a straight line so that year-5 growth equals the terminal growth rate of {g}.
3. EBIT, D&A, capital expenditures and net working capital are each held at their average share of revenue; each average is the simple mean of the three annual ratios (FY{fy0}-FY{fy}).
4. Net working capital = accounts receivable + inventories - accounts payable. The change in NWC each year = NWC share of revenue x (that year's revenue - the prior year's revenue), with FY{fy} revenue as the base.
{tax}
6. Year 5 is a steady-state year: capital expenditures = year-5 D&A x (1 + {g}), and the change in NWC = {g} x year-5 NWC.
7. FCFF = EBIT x (1 - tax) + D&A - capital expenditures - change in NWC."""

TAX_TEXTBOOK = "5. Tax: 21% (US federal statutory rate) on EBIT in every year."
TAX_PRAC = ("5. Tax on EBIT in years 1 to 4: the effective tax rate, the simple mean of the annual rates (income tax expense / "
            "income before income taxes) for FY{fy0}-FY{fy}, counting only years with positive income before taxes, held between "
            "10% and 35%. Year 5 uses the 21% US federal statutory rate.")

A8_TEXTBOOK = ("8. Cost of equity: CAPM with the 3-month Treasury bill rate as the risk-free rate and an equity risk premium of 7.00% "
               "(over bills). Beta: the unlevered industry beta relevered with Hamada, beta_L = beta_U x (1 + (1 - 21%) x D/E), with D/E at market values.")
A8_PRAC = ("8. Cost of equity: CAPM with the 10-year Treasury yield as the risk-free rate and an equity risk premium of 5.00% "
           "(Kroll recommended). Beta: the unlevered industry beta relevered with Hamada, beta_L = beta_U x (1 + (1 - 21%) x D/E), "
           "with D/E at market values, then Blume-adjusted: 0.67 x beta_L + 0.33.")
A9_11 = """9. Debt (D) = borrowings + lease liabilities, at book value. Equity (E) = market value of equity.
10. Pre-tax cost of debt = 10-year Treasury yield + the default spread for the synthetic rating. After-tax cost of debt uses 21%.
11. WACC with market-value weights D/(D+E) and E/(D+E)."""
A12_14_TEXTBOOK = """12. Year-end discounting: year t is discounted t years at the WACC.
13. Terminal value at the end of year 5 by the Gordon growth model: year-5 FCFF x (1 + 2.0%) / (WACC - 2.0%), discounted 5 years.
14. Equity value = enterprise value + cash and short-term investments (all treated as excess cash) - borrowings - lease liabilities - preferred stock - minority interest."""
A12_14_PRAC = """12. Mid-year discounting: year t is discounted t - 0.5 years at the WACC.
13. Terminal value at the end of year 5 by the Gordon growth model: year-5 FCFF x (1 + 2.5%) / (WACC - 2.5%), discounted 4.5 years.
14. Equity value = enterprise value + excess cash - borrowings - lease liabilities - preferred stock - minority interest, where excess cash = cash and short-term investments minus operating cash of 2% of FY{fy} revenue (not below zero)."""
A15 = "15. Value per share = equity value / FY{fy} weighted-average diluted shares."


def item(qid, n, kind, pts, crit, target, unit, tol_type, tol_value, step, comp, ck):
    tol = {"abs_pp": "+/-0.01 percentage points", "rel": "+/-1% of the target", "none": "n/a"}[tol_type]
    if comp == "Beta / Cost of equity model" and unit == "beta":
        tol = "+/-1% of the target (ratio, not in the scheme; see notes)"
    return dict(question_id=qid, item=n, kind=kind, points=pts, criterion=crit, target=target, unit=unit,
                tolerance=tol, tol_type=tol_type, tol_value=tol_value, step=step, component=comp, checkpoint=ck,
                source="stored checkpoint" if not str(ck).startswith(("derived", "alt")) else "derived from stored case")


def forecast_items(qid, c, start, include_final_fcff5):
    ck, f = c["checkpoints"], c["checkpoints"]["forecast"]
    S2, S3 = "Step 2. Project the future", "Step 3. Compute free cash flow"
    r1 = f["revenue"][0]
    rows = [
        item(qid, 0, "middle", 2, f"Year-1 revenue growth = {f['growth'][0]*100:.2f}%", round(f["growth"][0] * 100, 4), "%", "abs_pp", 0.01, S2, "Growth path", "forecast.growth.1"),
        item(qid, 0, "middle", 2, f"EBIT margin (mean of three ratios) = {f['ebit'][0]/r1*100:.2f}%", round(f["ebit"][0] / r1 * 100, 4), "%", "abs_pp", 0.01, S2, "Operating margin", "derived: forecast.ebit[1] / forecast.revenue[1]"),
        item(qid, 0, "middle", 2, f"D&A share of revenue = {f['da'][0]/r1*100:.2f}%", round(f["da"][0] / r1 * 100, 4), "%", "abs_pp", 0.01, S2, "Reinvestment (D&A)", "derived: forecast.da[1] / forecast.revenue[1]"),
        item(qid, 0, "middle", 2, f"Capex share of revenue = {f['capex'][0]/r1*100:.2f}%", round(f["capex"][0] / r1 * 100, 4), "%", "abs_pp", 0.01, S2, "Reinvestment (capex)", "derived: forecast.capex[1] / forecast.revenue[1]"),
        item(qid, 0, "middle", 2, f"NWC share of revenue = {f['nwc'][0]/r1*100:.2f}%", round(f["nwc"][0] / r1 * 100, 4), "%", "abs_pp", 0.01, S2, "Working capital", "derived: forecast.nwc[1] / forecast.revenue[1]"),
    ]
    if c["policy_label"] == "practitioner":
        rows.append(item(qid, 0, "middle", 2, f"Effective tax rate on EBIT (years 1-4) = {ck['tax_rate']*100:.2f}%", round(ck["tax_rate"] * 100, 4), "%", "abs_pp", 0.01, S2, "Tax applied", "tax_rate"))
    for t in range(5):
        last = t == 4 and include_final_fcff5
        rows.append(item(qid, 0, "final" if last else "step", 10 if last else 5, f"FCFF year {t+1} = ${money(ck['fcff'][t])} million",
                         round(ck["fcff"][t] / M, 4), "$ millions", "rel", 0.01, S3, "FCFF build", f"fcff.{t+1}"))
    return rows


def value_items(qid, c, with_weights):
    ck = c["checkpoints"]
    S4, S5 = "Step 4. Discount to today", "Step 5. Value and decide"
    rows = [
        item(qid, 0, "middle", 2, f"Levered beta = {ck['beta_levered']:.4f}", round(ck["beta_levered"], 6), "beta", "rel", 0.01, S4, "Beta / Cost of equity model", "beta_levered"),
        item(qid, 0, "middle", 2, f"Cost of equity = {ck['re']*100:.2f}%", round(ck["re"] * 100, 4), "%", "abs_pp", 0.01, S4, "Beta / Cost of equity model", "re"),
        item(qid, 0, "middle", 2, f"Pre-tax cost of debt = {ck['rd']*100:.2f}%", round(ck["rd"] * 100, 4), "%", "abs_pp", 0.01, S4, "Cost of debt", "rd"),
    ]
    if with_weights:
        rows.append(item(qid, 0, "middle", 2, f"Equity weight {ck['weights']['E']*100:.2f}%, debt weight {ck['weights']['D']*100:.2f}%",
                         round(ck["weights"]["E"] * 100, 4), "%", "abs_pp", 0.01, S4, "Capital structure weights", "weights.E"))
    rows += [
        item(qid, 0, "step", 5, f"WACC = {ck['wacc']*100:.2f}%", round(ck["wacc"] * 100, 4), "%", "abs_pp", 0.01, S4, "WACC", "wacc"),
        item(qid, 0, "step", 5, f"Terminal value = ${money(ck['tv'])} million", round(ck["tv"] / M, 4), "$ millions", "rel", 0.01, S4, "Terminal value method", "tv"),
        item(qid, 0, "step", 5, f"Enterprise value = ${money(ck['ev'])} million", round(ck["ev"] / M, 4), "$ millions", "rel", 0.01, S4, "Enterprise value", "ev"),
    ]
    if c["policy_label"] == "practitioner":
        rows.append(item(qid, 0, "middle", 2, f"Excess cash = cash and short-term investments - 2% of FY{c['inputs']['fiscal_years'][-1]} revenue = ${money(ck['cash_excess'])} million",
                         round(ck["cash_excess"] / M, 4), "$ millions", "rel", 0.01, S5, "Cash", "cash_excess"))
    basic = ck["equity"] / c["inputs"]["shares_basic"]
    rows += [
        item(qid, 0, "middle", 2, f"Equity value = ${money(ck['equity'])} million", round(ck["equity"] / M, 4), "$ millions", "rel", 0.01, S5, "Bridge to equity", "equity"),
        item(qid, 0, "final", 10, f"Value per share = ${ck['price_per_share']:.2f}", round(ck["price_per_share"], 4), "$ per share", "rel", 0.01, S5, "Value per share", "price_per_share"),
        item(qid, 0, "alternative", 0, f"Alternative, not scored: value per share on the latest basic share count ({c['inputs']['shares_basic']/M:,.3f} million shares) = ${basic:.2f}",
             round(basic, 4), "$ per share", "rel", 0.01, S5, "Share count", "alt: equity / inputs.shares_basic"),
    ]
    return rows


def figures_block(c, policy):
    i = c["inputs"]
    fy = i["fiscal_years"]
    vd = c["valuation_date"]
    lines = [
        f"- Total revenue: FY{fy[0]} ${money(i['revenue'][0])}, FY{fy[1]} ${money(i['revenue'][1])}, FY{fy[2]} ${money(i['revenue'][2])} million",
        f"- Operating income (EBIT): FY{fy[0]} ${money(i['ebit'][0])}, FY{fy[1]} ${money(i['ebit'][1])}, FY{fy[2]} ${money(i['ebit'][2])} million{zero_note(c, 'ebit')}",
        f"- Depreciation and amortization: FY{fy[0]} ${money(i['da'][0])}, FY{fy[1]} ${money(i['da'][1])}, FY{fy[2]} ${money(i['da'][2])} million{zero_note(c, 'da')}",
        f"- Capital expenditures (purchases of property, plant and equipment): FY{fy[0]} ${money(i['capex'][0])}, FY{fy[1]} ${money(i['capex'][1])}, FY{fy[2]} ${money(i['capex'][2])} million{zero_note(c, 'capex')}",
        f"- Accounts receivable: FY{fy[0]} ${money(i['receivables'][0])}, FY{fy[1]} ${money(i['receivables'][1])}, FY{fy[2]} ${money(i['receivables'][2])} million{zero_note(c, 'receivables')}",
        f"- Inventories: FY{fy[0]} ${money(i['inventory'][0])}, FY{fy[1]} ${money(i['inventory'][1])}, FY{fy[2]} ${money(i['inventory'][2])} million{zero_note(c, 'inventory')}",
        f"- Accounts payable: FY{fy[0]} ${money(i['payables'][0])}, FY{fy[1]} ${money(i['payables'][1])}, FY{fy[2]} ${money(i['payables'][2])} million{zero_note(c, 'payables')}",
    ]
    if policy == "practitioner":
        lines += [
            f"- Income before income taxes: FY{fy[0]} ${money(i['pretax_income'][0])}, FY{fy[1]} ${money(i['pretax_income'][1])}, FY{fy[2]} ${money(i['pretax_income'][2])} million",
            f"- Income tax expense: FY{fy[0]} ${money(i['tax_expense'][0])}, FY{fy[1]} ${money(i['tax_expense'][1])}, FY{fy[2]} ${money(i['tax_expense'][2])} million",
        ]
    lines += [
        f"- Cash and cash equivalents at the end of FY{fy[2]}: ${money(i['cash'])} million{zero_note(c, 'cash')}",
        f"- Short-term investments at the end of FY{fy[2]}: ${money(i['st_investments'] or 0)} million{zero_note(c, 'st_investments')}",
        f"- Borrowings (short-term and long-term debt) at the end of FY{fy[2]}: ${money(i['debt_total'])} million{debt_note(c)}",
        f"- Lease liabilities at the end of FY{fy[2]}: ${money(i['lease_liability'] or 0)} million{zero_note(c, 'lease_liability')}",
        f"- Preferred stock at the end of FY{fy[2]}: ${money(i['preferred'] or 0)} million{zero_note(c, 'preferred')}",
        f"- Minority (noncontrolling) interest at the end of FY{fy[2]}: ${money(i['minority_interest'] or 0)} million{zero_note(c, 'minority_interest')}",
        f"- FY{fy[2]} weighted-average diluted shares: {i['shares_diluted']/M:,.3f} million",
        f"- Market value of equity on {vd}: ${money(i['market_cap'])} million (share price ${i['price']:.2f} x basic shares outstanding)",
    ]
    if policy == "textbook":
        lines.append(f"- 3-month Treasury bill rate on {vd}: {pct(i['rates']['DTB3'])}")
    lines += [
        f"- 10-year Treasury yield on {vd}: {pct(i['rates']['DGS10'])}",
        f"- Synthetic credit rating (from EBIT over interest expense): {i['rating']}, default spread {pct(i['rates']['oas_rating'])}",
        f"- Damodaran unlevered industry beta ({c['company']['industry_damodaran']}): {i['beta_unlevered_industry']:.4f}",
    ]
    return "\n".join(lines)


def filing_line(c):
    p = c["inputs"]["provenance"]["revenue"]
    last = p[-1] if isinstance(p, list) else p
    return last.get("filed", "")


def q_full(c, qid, tier):
    pol = c["policy_label"]
    i, ck = c["inputs"], c["checkpoints"]
    fy = i["fiscal_years"]
    co = c["company"]["name"]
    g = "2.5%" if pol == "practitioner" else "2.0%"
    tax = TAX_PRAC.format(fy0=fy[0], fy=fy[2]) if pol == "practitioner" else TAX_TEXTBOOK
    head = (f"Value {co} as of {c['valuation_date']} with a free cash flow to the firm (FCFF) DCF"
            + (", using practitioner conventions" if pol == "practitioner" else "")
            + f". Use the historical figures below for fiscal years {fy[0]} to {fy[2]} (from its Form 10-K for fiscal {fy[2]}, filed {filing_line(c)}).")
    body = "\n".join([head, ASSUMPTIONS_1_7.format(fy=fy[2], fy0=fy[0], g=g, tax=tax),
                      A8_PRAC if pol == "practitioner" else A8_TEXTBOOK, A9_11,
                      (A12_14_PRAC if pol == "practitioner" else A12_14_TEXTBOOK).format(fy=fy[2]), A15.format(fy=fy[2]),
                      "Figures (use these as stated):", figures_block(c, pol)])
    if pol == "practitioner":
        report = ("Report the effective tax rate and the WACC (% to two decimals), FCFF for each year, the terminal value, the enterprise value, "
                  "excess cash and the equity value (all in $ millions to one decimal), and the value per share (dollars to two decimals).")
        fa = (f"Tax {ck['tax_rate']*100:.2f}%; WACC {ck['wacc']*100:.2f}%; FCFF years 1-5 " + ", ".join(f"${money(v)}" for v in ck["fcff"])
              + f" million; terminal value ${money(ck['tv'])} million; enterprise value ${money(ck['ev'])} million; equity value ${money(ck['equity'])} million; ${ck['price_per_share']:.2f} per share")
    else:
        report = ("Report the WACC (% to two decimals), FCFF for each year, the terminal value, the enterprise value and the equity value "
                  "(all in $ millions to one decimal), and the value per share (dollars to two decimals).")
        fa = (f"WACC {ck['wacc']*100:.2f}%; FCFF years 1-5 " + ", ".join(f"${money(v)}" for v in ck["fcff"])
              + f" million; terminal value ${money(ck['tv'])} million; enterprise value ${money(ck['ev'])} million; equity value ${money(ck['equity'])} million; ${ck['price_per_share']:.2f} per share")
    rub = forecast_items(qid, c, 0, False) + value_items(qid, c, True)
    rub.append(item(qid, 0, "rounding", 1, "Follows the rounding instruction: " + ("rates in % to two decimals" if pol == "practitioner" else "WACC % to two decimals")
                    + "; dollar amounts in $ millions to one decimal; value per share to two decimals", None, "", "none", None,
                    "Step 5. Value and decide", "Answer format", "n/a"))
    return dict(level=3, level_name="Full DCF", step="Steps 1-5", component="Full DCF" + (" (practitioner)" if pol == "practitioner" else ""),
                question=body + "\n" + report, final_answer=fa, unit="$ per share", tier=tier), rub


def q_half_a(c, qid, tier):
    i, ck = c["inputs"], c["checkpoints"]
    fy = i["fiscal_years"]
    co = c["company"]["name"]
    hist = (f"{co}, valuation date {c['valuation_date']}. Historical figures for fiscal years {fy[0]}, {fy[1]} and {fy[2]}, in that order: "
            f"Total revenue {three(i['revenue'])} million; Operating income (EBIT) {three(i['ebit'])} million{zero_note(c, 'ebit')}; "
            f"Depreciation and amortization {three(i['da'])} million{zero_note(c, 'da')}; Capital expenditures {three(i['capex'])} million{zero_note(c, 'capex')}; "
            f"Accounts receivable {three(i['receivables'])} million{zero_note(c, 'receivables')}; "
            f"Inventories {three(i['inventory'])} million{zero_note(c, 'inventory')}; "
            f"Accounts payable {three(i['payables'])} million{zero_note(c, 'payables')}.")
    body = hist + "\n" + ASSUMPTIONS_1_7.format(fy=fy[2], fy0=fy[0], g="2.0%", tax=TAX_TEXTBOOK)
    report = ("Report year-1 revenue growth and the four average shares of revenue (EBIT margin, D&A, capital expenditures and net working capital), "
              "each as a percentage to two decimals, and FCFF for years 1 to 5 in $ millions to one decimal.")
    fa = "FCFF years 1-5 " + ", ".join(f"${money(v)}" for v in ck["fcff"]) + " million"
    rub = forecast_items(qid, c, 0, True)
    rub.append(item(qid, 0, "rounding", 1, "Follows the rounding instruction: percentages to two decimals; FCFF in $ millions to one decimal",
                    None, "", "none", None, "Step 3. Compute free cash flow", "Answer format", "n/a"))
    return dict(level=4, level_name="Half DCF A (Steps 2-3)", step="Steps 2-3", component="Half DCF A: forecast and FCFF",
                question=body + "\n" + report, final_answer=fa, unit="$ millions", tier=tier), rub


def q_half_b(c, qid, tier):
    i, ck = c["inputs"], c["checkpoints"]
    fy = i["fiscal_years"]
    vd = c["valuation_date"]
    co = c["company"]["name"]
    head = (f"{co}, valuation date {vd}. Forecast free cash flow to the firm (FCFF) for years 1 to 5: "
            + ", ".join(f"${money(v)}" for v in ck["fcff"]) + " million.\n"
            f"Inputs: 3-month Treasury bill rate on {vd}: {pct(i['rates']['DTB3'])}; 10-year Treasury yield on {vd}: {pct(i['rates']['DGS10'])}; "
            f"synthetic credit rating {i['rating']}, default spread {pct(i['rates']['oas_rating'])}; "
            f"Damodaran unlevered industry beta ({c['company']['industry_damodaran']}): {i['beta_unlevered_industry']:.4f}; "
            f"market value of equity ${money(i['market_cap'])} million; borrowings ${money(i['debt_total'])} million; "
            f"lease liabilities ${money(i['lease_liability'] or 0)} million; cash and cash equivalents ${money(i['cash'])} million; "
            f"short-term investments ${money(i['st_investments'] or 0)} million; preferred stock ${money(i['preferred'] or 0)} million; "
            f"minority (noncontrolling) interest ${money(i['minority_interest'] or 0)} million; "
            f"FY{fy[2]} weighted-average diluted shares {i['shares_diluted']/M:,.3f} million.")
    body = "\n".join([head, "Assumptions:", A8_TEXTBOOK, A9_11, A12_14_TEXTBOOK, A15.format(fy=fy[2])])
    report = ("Report the levered beta (four decimals), the cost of equity, the pre-tax cost of debt and the WACC (% to two decimals), "
              "the terminal value, the enterprise value and the equity value ($ millions to one decimal), and the value per share (dollars to two decimals).")
    fa = (f"Beta {ck['beta_levered']:.4f}; cost of equity {ck['re']*100:.2f}%; cost of debt {ck['rd']*100:.2f}%; WACC {ck['wacc']*100:.2f}%; "
          f"terminal value ${money(ck['tv'])} million; enterprise value ${money(ck['ev'])} million; equity value ${money(ck['equity'])} million; ${ck['price_per_share']:.2f} per share")
    rub = value_items(qid, c, False)
    rub.append(item(qid, 0, "rounding", 1, "Follows the rounding instruction: beta to four decimals; rates in % to two decimals; dollar amounts in $ millions to one decimal; value per share to two decimals",
                    None, "", "none", None, "Step 5. Value and decide", "Answer format", "n/a"))
    return dict(level=5, level_name="Half DCF B (Steps 4-5)", step="Steps 4-5", component="Half DCF B: discount rate and value",
                question=body + "\n" + report, final_answer=fa, unit="$ per share", tier=tier), rub


def check_against_engine(c, rubric):
    """Every money/rate target must equal the independent engine within 0.02%."""
    from dcf_independent import checkpoint_value
    eng = value_case(c, c["policy_label"])
    bad = []
    for r in rubric:
        if r["kind"] in ("rounding",):
            continue
        v = checkpoint_value(eng, r["checkpoint"])
        if v is None:
            bad.append((r["question_id"], r["checkpoint"], "unmapped"))
            continue
        t = float(r["target"])
        if abs(v - t) > max(2e-4 * abs(t), 6e-4):
            bad.append((r["question_id"], r["checkpoint"], t, v))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "..", "data", "cases_v1_us", "cases.jsonl"))
    ap.add_argument("--v2", default=os.path.join(HERE, "..", "data", "QA_set_v2.json"))
    ap.add_argument("--dates", default="2019-12-31,2022-12-31")
    ap.add_argument("--new-companies", action="store_true", help="companies NOT in v2 (default: the 20 v2 tier companies)")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "data", "questions", "QA_set_ver03.json"))
    ap.add_argument("--keep-inspect", action="store_true",
                    help="keep company-dates listed in inspect.csv (outside the 0.3x-3x sanity band); v2 has none of them")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists; not overwriting")
    v2 = json.load(open(a.v2))
    v2_cos = v2["meta"]["companies"]
    cases = collections.defaultdict(dict)
    for line in open(a.cases):
        c = json.loads(line)
        cases[(c["company"]["ticker"], c["valuation_date"])][c["policy_label"]] = c
    dates = a.dates.split(",")
    inspect = set()
    ip = os.path.join(os.path.dirname(a.cases), "inspect.csv")
    if os.path.exists(ip) and not a.keep_inspect:
        import csv as _csv
        inspect = {r["case_id"] for r in _csv.DictReader(open(ip))}
    if a.new_companies:
        tickers = sorted({t for (t, d) in cases if d in dates} - set(v2_cos) - set(v2["meta"]["companies_basic_only"]))
    else:
        tickers = v2_cos
    questions, rubric, used, skipped, problems = [], [], [], [], []
    for d in dates:
        yr = d[:4]
        for tk in tickers:
            pair = cases.get((tk, d), {})
            if not {"textbook", "practitioner"} <= set(pair):
                skipped.append(f"{tk} {d}: no {'/'.join(sorted({'textbook','practitioner'} - set(pair)))} case")
                continue
            flagged = [pol for pol in ("textbook", "practitioner") if pair[pol]["case_id"] in inspect]
            if flagged:
                skipped.append(f"{tk} {d}: {'/'.join(flagged)} case outside the 0.3x-3x sanity band (inspect.csv)")
                continue
            for suffix, builder, pol, tier in (("05", q_full, "textbook", f"basic@{yr}"), ("06", q_half_a, "textbook", f"half@{yr}"),
                                               ("07", q_half_b, "textbook", f"half@{yr}"), ("08", q_full, "practitioner", f"complex@{yr}")):
                c = pair[pol]
                qid = f"{tk}-{yr}-{suffix}"
                q, rub = builder(c, qid, tier)
                for n, r in enumerate(rub, 1):
                    r["item"] = n
                problems += check_against_engine(c, rub)
                q.update(question_id=qid, ticker=tk, company=c["company"]["name"], sector=c["company"].get("gics_sector"),
                         valuation_date=d, case_id=c["case_id"], policy=pol,
                         total_points=sum(int(r["points"] or 0) for r in rub))
                order = ["question_id", "level", "level_name", "ticker", "company", "sector", "valuation_date", "case_id", "policy",
                         "step", "component", "question", "final_answer", "unit", "total_points", "tier"]
                questions.append({k: q[k] for k in order})
                rubric += rub
            used.append(dict(ticker=tk, valuation_date=d, case_id_textbook=pair["textbook"]["case_id"],
                             case_id_practitioner=pair["practitioner"]["case_id"], snapshot_id=pair["textbook"]["snapshot_id"],
                             model_value_per_share=round(pair["textbook"]["checkpoints"]["price_per_share"], 2),
                             market_price=round(pair["textbook"]["inputs"]["price"], 2)))
    if problems:
        print("ANSWER KEY DISAGREES WITH THE INDEPENDENT ENGINE:")
        for p in problems[:30]:
            print("  ", p)
        sys.exit(1)
    meta = dict(name=os.path.splitext(os.path.basename(a.out))[0], built_by="build_questions.py", source_cases=os.path.relpath(os.path.abspath(a.cases), os.path.join(HERE, "..")),
                dates=dates, companies=tickers, new_companies=a.new_companies, points_scheme=v2["meta"]["points_scheme"],
                tolerances=v2["meta"]["tolerances"],
                tiers={"basic@YYYY": "Level 3 full DCF, textbook policy", "half@YYYY": "Level 4 (Steps 2-3) and Level 5 (Steps 4-5), textbook",
                       "complex@YYYY": "Level 3 full DCF, practitioner policy"},
                differences_from_v2=["Level 3 prints every figure in the question; no input items in the L3 rubric",
                                     "basic-share alternative item on every L3 and L5 question"],
                skipped=skipped, checked="every target equals the dcf-bench checkpoint and the independent engine (dcf_independent.py) within 0.02%")
    with open(a.out, "x") as f:
        json.dump(dict(meta=meta, questions=questions, rubric=rubric, cases_used=used), f, indent=1)
    cnt = collections.Counter((q["tier"], q["level"]) for q in questions)
    print(f"{len(questions)} questions, {len(rubric)} rubric rows -> {a.out}")
    for k, v in sorted(cnt.items()):
        print("  ", k, v)
    print("skipped:", len(skipped))


if __name__ == "__main__":
    main()
