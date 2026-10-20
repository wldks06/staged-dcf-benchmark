"""Audit every question-answer pair of a question set. Reads only; writes a report and CSVs.

    python audit_questions.py --qa ../data/questions/QA_set_v2.json \
        --cases ../data/cases_v1_us/cases.jsonl \
        --snapshot ../data/snapshot_subset \
        --out ../results/audit

Five checks, each written to its own CSV and summarised in <out>/QA_AUDIT_ver01_<set>.md:

A. Answer key vs an independent engine (dcf_independent.py, written from the question
   wording, not from dcf-bench). Every final / middle / step / alternative target and every
   historical input item is recomputed and compared.
B. Reproducible from the question text: the numbers a solver needs are looked up in the prompt
   (as printed, i.e. rounded) and the answer is recomputed from them; the gap is compared with
   the rubric tolerance. Full DCF questions (L3 to L5) are recomputed with every input rounded the
   way the prompts print them.
C. Raw filings: every historical input and every Level 1 answer is matched to the SEC XBRL fact
   it came from (tag, period end, accession number) in the frozen snapshot; rates to FRED; the
   market value of equity to the stored close times basic shares. The Yahoo Finance closes are not
   redistributed with this repository (data/snapshot_subset/README.md); without them the
   market-value check is skipped. The published results in results/audit/ were produced with them.
D. Internal consistency of the rubric: points add up, the final_answer text shows the target at
   the stated rounding, every criterion's printed number matches its target, trap and
   alternative values are separated from the correct answer by more than the tolerance, and no
   scored item is silently dropped by the grader (zero target or target already in the prompt).
E. Flags carried by the source cases (outside the 0.3x-3x sanity band in inspect.csv, warnings).
"""
import argparse, collections, csv, gzip, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dcf_independent import value_case, checkpoint_value  # noqa: E402

NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def nums_in(text):
    out = []
    for m in NUM.finditer(text or ""):
        s = m.group(0).replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def tol_ok(v, t, tol_type, tol_value):
    tv = float(tol_value or 0)
    if tol_type == "exact":
        return abs(v - t) <= 0.05 + 1e-9
    if tol_type == "rel":
        return abs(v - t) <= abs(t) * tv + 1e-9
    if tol_type == "abs_pp":
        return abs(v - t) <= tv + 1e-9          # strict: no extra 0.005 slack here
    return True


def targets(t):
    if t is None or t == "":
        return []
    try:
        return [float(p.strip().replace(",", "")) for p in str(t).split(";")]
    except ValueError:
        return []


def write_csv(path, rows):
    if not rows:
        rows = [{"note": "no rows"}]
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- A. answer keys
def input_values(case):
    """Historical input items of the rubric, in $ millions (shares in millions)."""
    i = case["inputs"]
    yrs = i["fiscal_years"]
    out = {}
    for k in ("revenue", "ebit", "da", "capex", "receivables", "inventory", "payables",
              "tax_expense", "pretax_income", "interest_expense"):
        out[f"inputs.{k}.{yrs[0]}-{yrs[-1]}"] = [v / 1e6 for v in i[k]]
        for y, v in zip(yrs, i[k]):
            out[f"inputs.{k}.{y}"] = [v / 1e6]
    for k in ("cash", "st_investments", "debt_total", "lease_liability", "preferred", "minority_interest"):
        out[f"inputs.{k}"] = [(i[k] or 0) / 1e6]
    out["inputs.shares_diluted"] = [i["shares_diluted"] / 1e6]
    out["inputs.shares_basic"] = [i["shares_basic"] / 1e6]
    return out


def check_A(qa, cases, engines):
    rows = []
    qm = {q["question_id"]: q for q in qa["questions"]}
    for r in qa["rubric"]:
        if r["kind"] not in ("final", "middle", "step", "alternative", "input"):
            continue
        q = qm[r["question_id"]]
        case = cases[q["case_id"]]
        eng = engines[q["case_id"]]
        ts = targets(r["target"])
        if not ts:
            continue
        ck = (r["checkpoint"] or "").strip()
        vals = input_values(case).get(ck)
        if vals is None:
            v = checkpoint_value(eng, ck)
            vals = None if v is None else [v]
        if vals is None or len(vals) != len(ts):
            rows.append(dict(question_id=r["question_id"], item=r["item"], kind=r["kind"], checkpoint=ck,
                             target=r["target"], independent="", status="NOT CHECKED (unmapped checkpoint)"))
            continue
        worst = max(abs(v - t) / max(abs(t), 1e-9) if abs(v - t) > 6e-4 else 0.0 for v, t in zip(vals, ts))
        status = "match" if worst <= 2e-4 else "MISMATCH"
        if status == "MISMATCH" and r["kind"] == "input" and all(abs(v - t) <= 0.0501 for v, t in zip(vals, ts)):
            status = "match"          # filing reported in thousands; target is the value shown to $0.1 million
        rows.append(dict(question_id=r["question_id"], item=r["item"], kind=r["kind"], checkpoint=ck,
                         target=r["target"], independent="; ".join(f"{v:.6g}" for v in vals),
                         rel_gap=f"{worst:.2e}", status=status))
    return rows


# ---------------------------------------------------------------- B. reproducible from the prompt
def nearest(prompt_vals, v, money):
    """Prompt number that is v as printed (rounded), or None."""
    best = None
    for p in prompt_vals:
        tol = max(0.051, abs(v) * 5e-6) if money else max(0.0051, abs(v) * 5e-5)
        if abs(p - v) <= tol and (best is None or abs(p - v) < abs(best - v)):
            best = p
    return best


def recompute_L2(ck, eng, pv, q):
    """Recompute an L2 final from numbers found in the prompt. Returns (value, missing list)."""
    x = eng["inputs"]
    miss = []

    def get(name, v, money=True):
        p = nearest(pv, v, money)
        if p is None:
            miss.append(name)
            return v
        return p

    g = eng["g"] / 100
    has = lambda v, money=True: nearest(pv, v, money)
    if ck == "re":
        rf = get("risk-free", eng["rf"], False)
        erp = get("ERP", eng["erp"], False)
        bl = has(eng["beta_levered"], False)
        if bl is not None and has(x["beta_u"], False) is None:      # template gives the levered beta
            return rf + bl * erp, miss
        bu = get("unlevered beta", x["beta_u"], False)
        Dtot = x["debt"] + x["leases"]
        dcap = has(100 * Dtot / (Dtot + x["market_cap"]), False)     # template gives D/(D+E) in %
        if dcap is not None and has(x["market_cap"]) is None:
            de = (dcap / 100) / (1 - dcap / 100)
            return rf + bu * (1 + 0.79 * de) * erp, miss
        E = get("market equity", x["market_cap"])
        D = has(Dtot)
        if D is None:
            D = get("borrowings", x["debt"]) + get("leases", x["leases"]) if x["leases"] else get("total debt", Dtot)
        return rf + bu * (1 + 0.79 * D / E) * erp, miss
    if ck == "wacc":
        re_ = get("cost of equity", eng["re"], False)
        rd = has(eng["rd"], False)
        if rd is None:                                              # template gives 10-year yield + spread
            rd = get("10-year yield", x["dgs10"], False) + get("spread", x["spread"], False)
        E = get("market equity", x["market_cap"])
        Dtot = x["debt"] + x["leases"]
        D = nearest(pv, Dtot, True)
        if D is None:
            D = get("borrowings", x["debt"]) + (get("leases", x["leases"]) if x["leases"] else 0)
        return E / (D + E) * re_ + D / (D + E) * rd * 0.79, miss
    if ck == "fcff.1":
        da = get("D&A y1", eng["da"][1])
        e = has(eng["ebit"][1])
        if e is None:                                               # template gives EBITDA
            e = get("EBIT or EBITDA y1", eng["ebit"][1] + eng["da"][1]) - da
        cx = get("capex y1", eng["capex"][1])
        dn = has(abs(eng["dnwc"][1]))
        if dn is not None:
            dn = dn if eng["dnwc"][1] >= 0 else -dn
        elif has(eng["shares"]["nwc"], False) is not None:          # template gives NWC % and revenues
            rev0 = x["revenue"][2]
            dn = has(eng["shares"]["nwc"], False) / 100 * (get("revenue y1", eng["revenue"][1]) - get("revenue base", rev0))
        else:                                                       # template gives NWC levels
            nwc0 = eng["nwc"][1] - eng["dnwc"][1]
            dn = get("NWC year 1", eng["nwc"][1]) - get("NWC base year", nwc0)
        return e * 0.79 + da - cx - dn, miss
    if ck == "fcff.5":
        e = get("EBIT y5", eng["ebit"][5]); da = get("D&A y5", eng["da"][5])
        nwc = has(eng["nwc"][5])
        if nwc is None:
            share = has(eng["shares"]["nwc"], False)               # template gives NWC % of revenue
            if share is not None:
                nwc = share / 100 * get("revenue y5", eng["revenue"][5])
        dn = g * nwc if nwc is not None else get("dNWC y5", eng["dnwc"][5])
        return e * 0.79 + da - da * (1 + g) - dn, miss
    if ck == "tv":
        f5 = get("FCFF y5", eng["fcff"][5]); w = get("WACC", eng["wacc"], False) / 100
        return f5 * (1 + g) / (w - g), miss
    if ck == "price_per_share":
        ev = get("EV", eng["ev"])
        cash_all = x["cash"] + x["st_investments"]
        c = nearest(pv, cash_all, True)
        if c is None:
            c = get("cash", x["cash"]) + (get("ST investments", x["st_investments"]) if x["st_investments"] else 0)
        net_debt = has(x["debt"] + x["leases"] - cash_all)
        if net_debt is not None and has(x["debt"]) is None:         # template gives net debt
            debt, lease = net_debt + c, 0.0
        else:
            debt = has(x["debt"])
            if debt is None:                                        # template splits long- and short-term debt
                parts = [p for p in pv if 0 < p < x["debt"]]
                pair = [(p, q) for i, p in enumerate(parts) for q in parts[i + 1:] if abs(p + q - x["debt"]) <= 0.11]
                debt = sum(pair[0]) if pair else get("borrowings", x["debt"])
            lease = get("leases", x["leases"]) if x["leases"] else 0.0
        pref = get("preferred", x["preferred"]) if x["preferred"] else 0.0
        mino = get("minority", x["minority"]) if x["minority"] else 0.0
        sh = get("diluted shares", x["shares_diluted"])
        return (ev + c - debt - lease - pref - mino) / sh, miss
    if ck in ("ev", "pv_fcff"):
        w = get("WACC", eng["wacc"], False) / 100
        pvf = has(eng["pv_fcff"])
        if ck == "ev" and pvf is not None:                          # template gives PV of FCFF and TV
            return pvf + get("TV", eng["tv"]) / (1 + w) ** 5, miss
        fc = [get(f"FCFF y{t}", eng["fcff"][t]) for t in range(1, 6)]
        pv_f = sum(f / (1 + w) ** t for t, f in zip(range(1, 6), fc))
        if ck == "pv_fcff":
            return pv_f, miss
        tv = nearest(pv, eng["tv"], True)
        tv = tv if tv is not None else fc[4] * (1 + g) / (w - g)
        return pv_f + tv / (1 + w) ** 5, miss
    return None, ["template not covered"]


def check_B(qa, cases, engines):
    rows = []
    rub = collections.defaultdict(list)
    for r in qa["rubric"]:
        rub[r["question_id"]].append(r)
    for q in qa["questions"]:
        lvl = int(q["level"])
        if lvl == 1:
            continue
        fin = next(r for r in rub[q["question_id"]] if r["kind"] == "final")
        t = targets(fin["target"])[0]
        eng = engines[q["case_id"]]
        if lvl == 2:
            v, miss = recompute_L2(fin["checkpoint"], eng, nums_in(q["question"]), q)
            how = "L2 from prompt numbers"
        else:
            pol = "practitioner" if q["case_id"].endswith("practitioner") else "textbook"
            er = value_case(cases[q["case_id"]], pol, round_inputs=True)
            v, miss = checkpoint_value(er, fin["checkpoint"]), []
            how = "inputs rounded as printed"
        if v is None:
            rows.append(dict(question_id=q["question_id"], tier=q["tier"], level=lvl, checkpoint=fin["checkpoint"],
                             status="NOT CHECKED", note="; ".join(miss)))
            continue
        gap = abs(v - t)
        tol = float(fin["tol_value"] or 0) * (abs(t) if fin["tol_type"] == "rel" else 1)
        share = gap / tol if tol else (0 if gap <= 0.05 else 99)
        status = "ok" if share <= 0.5 else ("TIGHT (uses >50% of tolerance)" if share <= 1 else "NOT REPRODUCIBLE")
        if miss:
            status = "PARTLY CHECKED (number not found in prompt: " + ", ".join(miss) + ")"
        rows.append(dict(question_id=q["question_id"], tier=q["tier"], level=lvl, checkpoint=fin["checkpoint"],
                         target=f"{t:.6g}", from_prompt=f"{v:.6g}", gap=f"{gap:.4g}", tolerance=f"{tol:.4g}",
                         share_of_tolerance=f"{share:.2f}", method=how, status=status))
    return rows


# ---------------------------------------------------------------- C. raw filings
def load_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def check_C(qa, cases, snap):
    rows = []
    used = {q["case_id"] for q in qa["questions"]}
    facts_cache = {}
    for cid in sorted(used):
        c = cases[cid]
        if not cid.endswith("textbook"):
            continue                                  # practitioner cases share the inputs
        tk = c["company"]["ticker"]
        cik = c["company"]["cik"]
        fpath = os.path.join(snap, "edgar", "companyfacts", f"CIK{cik}.json.gz")
        if cik not in facts_cache:
            facts_cache[cik] = load_gz(fpath) if os.path.exists(fpath) else None
        cf = facts_cache[cik]
        prov = c["inputs"].get("provenance", {})
        for key, plist in prov.items():
            if not isinstance(plist, list):
                plist = [plist]
            for p in plist:
                if not isinstance(p, dict) or p.get("source") != "edgar":
                    continue
                tag = p.get("tag") or ""
                pref, _, name = tag.partition(":")
                status, raw = "NOT FOUND", ""
                if cf is None:
                    status = "NO COMPANYFACTS FILE"
                else:
                    units = cf["facts"].get(pref, {}).get(name, {}).get("units", {})
                    hits = [f for u in units.values() for f in u
                            if f.get("accn") == p.get("accn") and f.get("end") == p.get("period_end")]
                    if hits:
                        raw = hits[0]["val"]
                        status = "match" if abs(float(raw) - float(p["value"])) <= max(1.0, abs(p["value"]) * 1e-9) else "VALUE DIFFERS"
                        if hits[0].get("filed") != p.get("filed"):
                            status += " (filed date differs)"
                    elif units:
                        status = "TAG FOUND, NO FACT FOR THAT ACCESSION AND PERIOD"
                    elif "+" in tag or "derived" in str(p.get("note") or "").lower():
                        status = "DERIVED (not a single fact)"
                rows.append(dict(case_id=cid, ticker=tk, input=key, fiscal_year=p.get("fiscal_year"),
                                 tag=tag, accn=p.get("accn"), filed=p.get("filed"), period_end=p.get("period_end"),
                                 case_value=p.get("value"), raw_value=raw, status=status,
                                 filed_after_valuation_date="YES" if (p.get("filed") or "") > c["valuation_date"] else ""))
        # rates and market value
        vd = c["valuation_date"]
        for sid, key in (("DTB3", "DTB3"), ("DGS10", "DGS10")):
            fp = os.path.join(snap, "fred", f"{sid}.json.gz")
            if not os.path.exists(fp):
                continue
            obs = [o for o in load_gz(fp)["observations"] if o["date"] <= vd and o["value"] not in (".", "")]
            raw = float(obs[-1]["value"]) / 100 if obs else None
            st = c["inputs"]["rates"][key]
            rows.append(dict(case_id=cid, ticker=tk, input=f"rates.{key}", fiscal_year="", tag=f"FRED {sid} last obs <= {vd}",
                             accn="", filed=obs[-1]["date"] if obs else "", period_end=vd, case_value=st, raw_value=raw,
                             status="match" if raw is not None and abs(raw - st) < 1e-9 else "VALUE DIFFERS"))
        pp = os.path.join(snap, "prices", f"{tk}.json.gz")
        if os.path.exists(pp):
            pj = load_gz(pp)
            closes = [cl for cl in pj["closes"] if cl[0] <= vd]
            close = closes[-1][1] if closes else None
            # Yahoo closes are adjusted for later splits and spin-offs; the case builder undoes that
            # (engine/src/dcfbench/data/prices.py). Undo it here too with the split events after the date.
            factor = 1.0
            for ev in pj.get("splits") or []:
                d_, ratio = (ev[0], ev[1]) if isinstance(ev, (list, tuple)) else (ev.get("date"), ev.get("ratio"))
                if d_ and d_ > vd and ratio:
                    factor *= float(ratio)
            mc = c["inputs"]["market_cap"]
            implied = (close or 0) * factor * c["inputs"]["shares_basic"]
            if close and abs(implied - mc) <= mc * 1e-6:
                st = "match" if factor == 1.0 else f"match after undoing later split/spin-off factor {factor:.4g}"
            else:
                st = (f"DIFFERS (stored price {c['inputs']['price']:.4f}, raw close {close} x later split factor "
                      f"{factor:.4g}; check the adjustment)")
            rows.append(dict(case_id=cid, ticker=tk, input="market_cap = close x basic shares", fiscal_year="",
                             tag=f"Yahoo close {closes[-1][0] if closes else ''}", accn="", filed="", period_end=vd,
                             case_value=mc, raw_value=implied, status=st))
    return rows


# ---------------------------------------------------------------- D. rubric consistency
def fmt_like(t, unit_hint):
    return t


def check_D(qa):
    rows = []
    rub = collections.defaultdict(list)
    for r in qa["rubric"]:
        rub[r["question_id"]].append(r)
    for q in qa["questions"]:
        qid = q["question_id"]
        items = rub[qid]
        def add(check, status, detail=""):
            rows.append(dict(question_id=qid, tier=q["tier"], level=q["level"], check=check, status=status, detail=detail))
        pts = sum(int(r["points"] or 0) for r in items)
        add("total points = sum of rubric points", "ok" if pts == int(q["total_points"]) else "MISMATCH",
            f"{pts} vs {q['total_points']}")
        finals = [r for r in items if r["kind"] == "final"]
        add("exactly one final item", "ok" if len(finals) == 1 else "PROBLEM", str(len(finals)))
        if not finals:
            continue
        fin = finals[0]
        ft = targets(fin["target"])
        fa = nums_in(q["final_answer"])
        # final answer text shows the target (any printed number within half a unit of the last digit)
        shown = all(any(abs(a - t) <= max(0.0051, abs(t) * 0.0005) or abs(a - t) <= 0.051 for a in fa) for t in ft)
        add("final_answer text shows the final target", "ok" if shown else "CHECK", f"{q['final_answer'][:80]} | target {fin['target']}")
        prompt_vals = nums_in(q["question"])
        for r in items:
            ts = targets(r["target"])
            if r["kind"] in ("final", "middle", "step") and ts:
                crit_nums = nums_in(r["criterion"])
                ok = all(any(abs(c - t) <= max(0.0051, abs(t) * 0.0006) or abs(c - t) <= 0.051 for c in crit_nums) for t in ts)
                if not ok:
                    add(f"criterion text matches target (item {r['item']})", "CHECK", f"{r['criterion'][:90]} | target {r['target']}")
                if any(t == 0 for t in ts):
                    add(f"scored item has zero target (item {r['item']}, grader skips it)", "INFO", r["criterion"][:90])
                if r["kind"] != "input" and all(any(abs(v - t) <= max(0.0005 * abs(t), 0.005) for v in prompt_vals) for t in ts):
                    sev = "PROBLEM" if r["kind"] == "final" else "INFO"
                    add(f"target already printed in the prompt (item {r['item']}, grader skips it)", sev, r["criterion"][:90])
            if r["kind"] in ("trap", "alternative") and ts and ft:
                t0, f0 = ts[0], ft[0]
                tol = float(fin["tol_value"] or 0) * (abs(f0) if fin["tol_type"] == "rel" else 1)
                gap = abs(t0 - f0)
                status = "ok" if gap > 2 * tol else ("OVERLAPS correct answer" if gap <= tol else "CLOSE (within 2x tolerance)")
                add(f"{r['kind']} value separated from the correct answer", status,
                    f"gap {gap:.4g} vs tolerance {tol:.4g} | {r['criterion'][:70]}")
        if "round" not in q["question"].lower() and "decimal" not in q["question"].lower():
            add("question states the rounding", "CHECK", "")
    return rows


# ---------------------------------------------------------------- E. case flags
def check_E(qa, cases, cases_dir):
    rows = []
    insp = {}
    p = os.path.join(cases_dir, "inspect.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            insp[r.get("case_id", "")] = r
    for cid in sorted({q["case_id"] for q in qa["questions"]}):
        c = cases[cid]
        ck = c["checkpoints"]
        ratio = ck["price_per_share"] / c["inputs"]["price"] if c["inputs"]["price"] else None
        rows.append(dict(case_id=cid, model_price=round(ck["price_per_share"], 2), market_price=c["inputs"]["price"],
                         model_over_market=round(ratio, 2) if ratio else "",
                         tv_share=round(ck.get("tv_share") or 0, 3), in_inspect_csv="YES" if cid in insp else "",
                         warnings="; ".join(ck.get("warnings") or [])))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default=os.path.join(HERE, "..", "data", "QA_set_v2.json"))
    ap.add_argument("--cases", default=os.path.join(HERE, "..", "data", "cases_v1_us", "cases.jsonl"))
    ap.add_argument("--snapshot", default=os.path.join(HERE, "..", "data", "snapshot_subset"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "audit"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    qa = json.load(open(a.qa))
    cases = {}
    for line in open(a.cases):
        c = json.loads(line)
        cases[c["case_id"]] = c
    engines = {}
    for q in qa["questions"]:
        cid = q["case_id"]
        if cid not in engines:
            engines[cid] = value_case(cases[cid], "practitioner" if cid.endswith("practitioner") else "textbook")

    A, B, C, D, E = (check_A(qa, cases, engines), check_B(qa, cases, engines), check_C(qa, cases, a.snapshot),
                     check_D(qa), check_E(qa, cases, os.path.dirname(a.cases)))
    name = os.path.splitext(os.path.basename(a.qa))[0]
    for tag, rows in (("A_answer_keys", A), ("B_reproducible_from_prompt", B), ("C_raw_filings", C),
                      ("D_rubric_consistency", D), ("E_case_flags", E)):
        write_csv(os.path.join(a.out, f"{name}_{tag}.csv"), rows)

    def count(rows, key="status"):
        return collections.Counter(r.get(key, "") for r in rows)
    lines = [f"# QA audit ver01: {name}", "",
             f"Questions: {len(qa['questions'])}. Rubric rows: {len(qa['rubric'])}. Source cases: {os.path.relpath(os.path.abspath(a.cases), os.path.join(HERE, '..'))}.", "",
             "| Check | Result |", "|---|---|"]
    for tag, rows in (("A. Answer key vs independent engine", A), ("B. Reproducible from the question text", B),
                      ("C. Inputs vs raw SEC / FRED / price files", C)):
        lines.append(f"| {tag} | " + ", ".join(f"{k}: {v}" for k, v in count(rows).most_common()) + " |")
    dcount = collections.Counter((r["check"].split(" (item")[0], r["status"]) for r in D if r["status"] != "ok")
    lines.append("| D. Rubric consistency (non-ok only) | " +
                 (", ".join(f"{k[0]} = {k[1]}: {v}" for k, v in dcount.most_common()) or "all ok") + " |")
    lines.append(f"| E. Cases outside the 0.3x-3x band | {sum(1 for r in E if r['in_inspect_csv'])} of {len(E)} |")
    lines += ["", "Details per row are in the CSV files next to this report.", ""]
    for tag, rows, bad in (("A", A, lambda r: r["status"] != "match"),
                           ("B", B, lambda r: r["status"] != "ok"),
                           ("C", C, lambda r: not r["status"].startswith("match")),
                           ("D", D, lambda r: r["status"] not in ("ok", "INFO"))):
        sel = [r for r in rows if bad(r)]
        lines.append(f"## {tag}: rows that need a look ({len(sel)})")
        lines.append("")
        if sel:
            keys = list(sel[0].keys())
            lines.append("| " + " | ".join(keys) + " |")
            lines.append("|" + "---|" * len(keys))
            for r in sel[:60]:
                lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "/")[:90] for k in keys) + " |")
            if len(sel) > 60:
                lines.append(f"| ... {len(sel) - 60} more in the CSV |")
        else:
            lines.append("None.")
        lines.append("")
    with open(os.path.join(a.out, f"QA_AUDIT_ver01_{name}.md"), "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[:12]))
    print("Written to", a.out)


if __name__ == "__main__":
    main()
