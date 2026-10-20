"""Independent DCF engine, used only to check the answer keys.

Written from the wording of the questions (Assumptions 1-15), not by importing or copying the
dcf-bench engine (engine/src/dcfbench/engine.py), so that agreement between the two is real evidence that
the answer keys are right (paper, Section IV-B; results/audit/, check A).
Every function takes a case dict (one line of data/cases_v1_us/cases.jsonl) and returns plain floats in
the question set's units: money in $ millions, rates in percent, beta as a number.

    from dcf_independent import value_case
    out = value_case(case, policy="textbook")      # or "practitioner"
    out["price_per_share"], out["fcff"][1], out["wacc"], ...

`round_inputs=True` rounds every input to the precision a question shows it with ($0.1 million,
rates to 0.01 percentage point, beta to 4 decimals, shares to 0.001 million), to test whether the
answer can be reproduced from the numbers printed in the question.
"""
import math

STAT_TAX = 0.21          # Assumption 5 (textbook) and year 5 (practitioner)
M = 1e6                  # dollars per $ million


def _r(x, nd, on):
    return round(x, nd) if on else x


def inputs_millions(case, round_inputs=False):
    """Case inputs in the QA set's units. Lists are oldest year first (FY t-2, t-1, t)."""
    i = case["inputs"]
    ro = round_inputs
    mil = lambda v: _r((v or 0.0) / M, 1, ro)
    lst = lambda k: [mil(v) for v in i[k]]
    rates = i["rates"]
    pct = lambda v: _r(v * 100, 2, ro)
    return dict(
        years=i["fiscal_years"],
        revenue=lst("revenue"), ebit=lst("ebit"), da=lst("da"), capex=lst("capex"),
        receivables=lst("receivables"), inventory=lst("inventory"), payables=lst("payables"),
        tax_expense=lst("tax_expense"), pretax_income=lst("pretax_income"),
        interest_expense=lst("interest_expense"),
        cash=mil(i["cash"]), st_investments=mil(i["st_investments"]),
        debt=mil(i["debt_total"]), leases=mil(i["lease_liability"]),
        preferred=mil(i["preferred"]), minority=mil(i["minority_interest"]),
        book_equity=mil(i.get("book_equity")),
        shares_diluted=_r(i["shares_diluted"] / M, 3, ro), shares_basic=_r(i["shares_basic"] / M, 3, ro),
        price=i["price"], market_cap=mil(i["market_cap"]),
        dtb3=pct(rates["DTB3"]), dgs10=pct(rates["DGS10"]), spread=pct(rates["oas_rating"]),
        beta_u=_r(i["beta_unlevered_industry"], 4, ro), rating=i.get("rating"),
    )


def value_case(case, policy="textbook", round_inputs=False):
    x = inputs_millions(case, round_inputs)
    prac = policy == "practitioner"
    g = 2.5 if prac else 2.0                       # Assumption 2 / 6 (percent)
    gf = g / 100
    N = 5

    # Assumption 2: growth path
    rev = x["revenue"]
    cagr = (rev[2] / rev[0]) ** 0.5 - 1
    g1 = min(max(cagr, 0.0), 0.15)
    growth = {t: g1 + (gf - g1) * (t - 1) / (N - 1) for t in range(1, N + 1)}

    # Assumption 3 and 4: mean of three annual ratios
    nwc_hist = [a + b - c for a, b, c in zip(x["receivables"], x["inventory"], x["payables"])]
    mean = lambda num: sum(n / r for n, r in zip(num, rev)) / 3
    s_ebit, s_da, s_capex, s_nwc = mean(x["ebit"]), mean(x["da"]), mean(x["capex"]), mean(nwc_hist)

    # Assumption 5: tax on EBIT
    if prac:
        rates = [t / p for t, p in zip(x["tax_expense"], x["pretax_income"]) if p > 0]
        eff = min(max(sum(rates) / len(rates), 0.10), 0.35) if rates else STAT_TAX
        tax = {t: (eff if t < N else STAT_TAX) for t in range(1, N + 1)}
    else:
        eff = STAT_TAX
        tax = {t: STAT_TAX for t in range(1, N + 1)}

    f = {k: {} for k in ("revenue", "ebit", "da", "capex", "nwc", "dnwc", "fcff", "tax_rate", "growth")}
    prev = rev[2]
    for t in range(1, N + 1):
        r_t = prev * (1 + growth[t])
        f["growth"][t] = growth[t] * 100
        f["revenue"][t] = r_t
        f["ebit"][t] = s_ebit * r_t
        f["da"][t] = s_da * r_t
        f["nwc"][t] = s_nwc * r_t
        if t < N:
            f["capex"][t] = s_capex * r_t
            f["dnwc"][t] = s_nwc * (r_t - prev)
        else:                                       # Assumption 6: steady-state year
            f["capex"][t] = f["da"][t] * (1 + gf)
            f["dnwc"][t] = gf * f["nwc"][t]
        f["tax_rate"][t] = tax[t] * 100
        f["fcff"][t] = f["ebit"][t] * (1 - tax[t]) + f["da"][t] - f["capex"][t] - f["dnwc"][t]   # Assumption 7
        prev = r_t

    # Assumptions 8 to 11: cost of capital
    D = x["debt"] + x["leases"]
    E = x["market_cap"]
    rf = x["dgs10"] if prac else x["dtb3"]
    erp = 5.0 if prac else 7.0
    beta_hamada = x["beta_u"] * (1 + (1 - STAT_TAX) * D / E)
    beta = 0.67 * beta_hamada + 0.33 if prac else beta_hamada
    re = rf + beta * erp
    rd = x["dgs10"] + x["spread"]
    wE, wD = E / (D + E), D / (D + E)
    wacc = wE * re + wD * rd * (1 - STAT_TAX)
    w = wacc / 100

    # Assumptions 12 and 13: discounting and terminal value
    shift = 0.5 if prac else 0.0
    pv = {t: f["fcff"][t] / (1 + w) ** (t - shift) for t in range(1, N + 1)}
    tv = f["fcff"][N] * (1 + gf) / (w - gf)
    pv_tv = tv / (1 + w) ** (N - shift)
    ev = sum(pv.values()) + pv_tv

    # Assumption 14 and 15: bridge
    cash_all = x["cash"] + x["st_investments"]
    cash_excess = max(cash_all - 0.02 * rev[2], 0.0) if prac else cash_all
    equity = ev + cash_excess - x["debt"] - x["leases"] - x["preferred"] - x["minority"]

    return dict(
        policy=policy, g=g, growth=f["growth"], revenue=f["revenue"], ebit=f["ebit"], da=f["da"],
        capex=f["capex"], nwc=f["nwc"], dnwc=f["dnwc"], fcff=f["fcff"], tax_rate_by_year=f["tax_rate"],
        shares={"ebit": s_ebit * 100, "da": s_da * 100, "capex": s_capex * 100, "nwc": s_nwc * 100},
        tax_rate=eff * 100, rf=rf, erp=erp, beta_hamada=beta_hamada, beta_levered=beta, re=re, rd=rd,
        rd_after_tax=rd * (1 - STAT_TAX), weights={"E": wE * 100, "D": wD * 100}, de=D / E,
        wacc=wacc, pv=pv, pv_fcff=sum(pv.values()), tv=tv, pv_tv=pv_tv, ev=ev,
        cash_excess=cash_excess, equity=equity,
        price_per_share=equity / x["shares_diluted"], price_basic=equity / x["shares_basic"],
        inputs=x,
    )


def checkpoint_value(out, checkpoint):
    """Map a rubric `checkpoint` string to this engine's value (None when unmapped)."""
    c = (checkpoint or "").strip()
    x = out["inputs"]
    years = x["years"]
    simple = {
        "wacc": out["wacc"], "re": out["re"], "rd": out["rd"], "tv": out["tv"], "ev": out["ev"],
        "pv_fcff": out["pv_fcff"], "pv_tv": out["pv_tv"], "equity": out["equity"],
        "price_per_share": out["price_per_share"], "beta_levered": out["beta_levered"],
        "cash_excess": out["cash_excess"], "tax_rate": out["tax_rate"], "weights.E": out["weights"]["E"],
        "alt: equity / inputs.shares_basic": out["price_basic"],
        "derived: (inputs.debt_total + inputs.lease_liability) / inputs.market_cap": out["de"],
        "derived: rd x (1 - tax_rate)": out["rd_after_tax"],
        "derived: fcff.5 x (1 + g)": out["fcff"][5] * (1 + out["g"] / 100),
        "derived: fcff.1 / (1 + wacc)": out["fcff"][1] / (1 + out["wacc"] / 100),
        "derived: weights.D / weights.E": out["weights"]["D"] / out["weights"]["E"],
        "derived: forecast.ebit[1] x (1 - forecast.tax_rate[1])": out["ebit"][1] * (1 - out["tax_rate_by_year"][1] / 100),
        "derived: forecast.ebit[1] / forecast.revenue[1]": out["shares"]["ebit"],
        "derived: forecast.da[1] / forecast.revenue[1]": out["shares"]["da"],
        "derived: forecast.capex[1] / forecast.revenue[1]": out["shares"]["capex"],
        "derived: forecast.nwc[1] / forecast.revenue[1]": out["shares"]["nwc"],
        "derived: forecast.ebit[1]": out["ebit"][1], "derived: forecast.dnwc[1]": out["dnwc"][1],
        "derived: forecast.dnwc[5]": out["dnwc"][5], "derived: forecast.capex[5]": out["capex"][5],
        "forecast.growth.1": out["growth"][1],
    }
    if c in simple:
        return simple[c]
    if c.startswith("fcff.") and c[5:].isdigit():
        return out["fcff"][int(c[5:])]
    if c.startswith("inputs.") and c.count(".") == 2:          # inputs.revenue.2024
        _, k, yr = c.split(".")
        k = {"revenue": "revenue", "ebit": "ebit", "capex": "capex", "da": "da"}.get(k, k)
        if k in x and yr in years:
            return x[k][years.index(yr)]
    return None
