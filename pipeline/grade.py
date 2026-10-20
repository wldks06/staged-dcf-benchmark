"""Grade model answers against the rubric of a question set. Deterministic, no LLM judge. Reads only;
never overwrites.

    python grade.py --qa ../data/questions/QA_set_v2.json --answers <answers.jsonl[.gz]> ... \
        --tolerance qa --out ../results/graded/<preset>
    python grade.py --qa ../data/questions/QA_set_v2.json --self-test

How an answer is scored (paper, Section IV-E):
1. Numbers. Every number in the reply is extracted (with %, $, million / billion units). Middle and step
   items match any number of the reply; final, trap and alternative items match only the text after the
   final-answer marker.
2. Final-answer marker. The text after the LAST marker is used, in this order of kinds: "final answer:"
   (any case) > a "Final Response" or "Final Answer" heading or bold label > the last <answer> block > all
   \\boxed{} values. The financial fine-tunes rarely write the requested FINAL ANSWER line (DianJin-R1 writes
   \\boxed{...} inside <answer>...</answer>; Fin-R1 writes "**Final Answer**" and \\boxed{...}; TheFinAI's
   Fino1 / Fin-o1 write a "## Final Response" heading). An empty reply whose thinking holds an <answer> block
   or \\boxed{} (DianJin sometimes never closes </think>) is read from there. A reply with no marker at all
   scores zero on final, trap and alternative items. The summary reports the marker kinds.
3. Tolerances. --tolerance qa (the paper's headline) uses each rubric item's own tolerance: rates within
   0.01 percentage points (plus 0.005 pp slack for rounding), dollar values within 1%. --tolerance plan is a
   looser sensitivity check: value per share, enterprise value, terminal value, equity value and present
   values 2%; FCFF 1%; rates 0.10 pp; levered beta 0.02 absolute; capital-structure weights 1 pp; values
   pulled from filings 0.5%.
4. Trap and alternative items (0 points) count as a hit only when the final item is NOT correct, i.e. the
   answer is within tolerance of the trap figure and not within tolerance of the correct answer.
5. --include-thinking adds the model's reasoning trace to the number pool for middle and step items (never
   for final, trap or alternative items), so a reasoning model is not penalised for doing the work in its
   thinking block (paper, Section V-B, "when the reasoning trace is also searched").
6. Items that cannot be auto-graded are excluded, not failed: rounding items, inputs already given in the
   question, zero targets, and targets printed in the prompt.

Output files are graded_ver05_<mode>_<answers>.csv (one row per rubric item) and summary_ver05_<mode>_<answers>.txt,
with <mode> = qa, plan or plan_think ("ver05" is the grader version used in the paper). The scoring rules
descend from the pilot grader (pilot/grade.py); what changed is listed in docs/PIPELINE.md.
"""
import argparse, collections, csv, gzip, json, os, re, sys

NUM = re.compile(r"\(?-?\$?\s*\d[\d,]*\.?\d*\)?\s*(?:%|percent|billion|bn|million|mm|m\b|x\b)?", re.I)
MARK = re.compile(r"final\s+answer\s*:", re.I)
EXACT_MARK = "FINAL ANSWER:"
HEAD = re.compile(r"(?:#+\s*|\*\*)\s*final\s+(?:response|answer)\s*(?:\*\*)?\s*:?[^\S\n]*\n", re.I)
ANS = re.compile(r"<answer>(.*?)</answer>", re.S | re.I)
BOXED = re.compile(r"\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}")


def numbers(text):
    vals = []
    for m in NUM.finditer(text or ""):
        s = m.group(0)
        # unchanged from v3: a number written after a minus sign is read as negative
        neg = s.strip().startswith("(") and s.strip().rstrip("%xXmMnNbBiIlLoO ").endswith(")") or "-" in s
        core = re.sub(r"[^\d.]", "", re.sub(r"(?i)(billion|bn|million|mm|percent)", "", s))
        if not core or core == ".":
            continue
        try:
            v = float(core)
        except ValueError:
            continue
        v = -v if neg else v
        low = s.lower()
        vals.append((v, "billion" in low or re.search(r"\bbn\b", low) is not None, "%" in s or "percent" in low))
    return vals


def targets(t):
    if t is None or t == "":
        return []
    if isinstance(t, (int, float)):
        return [float(t)]
    out = []
    for part in str(t).split(";"):
        try:
            out.append(float(part.strip().replace(",", "")))
        except ValueError:
            pass
    return out


MONEY_2PCT = ("price_per_share", "ev", "tv", "equity", "pv_fcff", "pv_tv", "cash_excess",
              "alt: equity / inputs.shares_basic")


def tolerance(item, mode):
    """(tol_type, tol_value, slack) for an item under 'qa' or 'plan'."""
    tt, tv = item.get("tol_type"), float(item.get("tol_value") or 0)
    if mode == "qa":
        return tt, tv, (0.005 if tt == "abs_pp" else 0.0)
    ck = (item.get("checkpoint") or "").strip()
    if item.get("kind") == "input" or ck.startswith("inputs."):
        return "rel", 0.005, 0.0
    if ck == "beta_levered":
        return "abs", 0.02, 0.0
    if ck == "weights.E":
        return "abs_pp", 1.0, 0.0
    if ck in MONEY_2PCT or (item.get("kind") == "trap" and tt == "rel"):
        return "rel", 0.02, 0.0
    if tt == "abs_pp":
        return "abs_pp", 0.10, 0.0
    return tt, tv, 0.0


def close(v, t, tt, tv, slack):
    if tt == "exact":
        return abs(v - t) <= 0.05 + 1e-9
    if tt == "rel":
        return abs(v - t) <= abs(t) * tv + 1e-9 or (t == 0 and abs(v) < 1e-6)
    if tt in ("abs_pp", "abs"):
        return abs(v - t) <= tv + slack + 1e-9
    return False


def matches(vals, t, item, mode):
    unit = (item.get("unit") or "").lower()
    tt, tv, slack = tolerance(item, mode)
    for v, is_bn, is_pct in vals:
        cands = [v]
        if unit == "%" and not is_pct:
            cands.append(v * 100)
        if "$ millions" in unit and is_bn:
            cands = [v * 1000]
        if any(close(c, t, tt, tv, slack) for c in cands):
            return True
    return False


def split_final(resp, thinking=""):
    """(text that holds the final answer or None, marker kind)."""
    resp = resp or ""
    ms = list(MARK.finditer(resp))
    if ms:
        m = ms[-1]
        return resp[m.end():], ("exact" if resp[m.start():m.end()] == EXACT_MARK else "other case")
    hs = list(HEAD.finditer(resp))
    if hs:
        return resp[hs[-1].end():], "Final Response heading"
    a = ANS.findall(resp)
    if a:
        return a[-1], "answer tag"
    b = BOXED.findall(resp)
    if b:
        return " ; ".join(b), "boxed"
    if not resp.strip() and thinking:                  # reply empty: the model never closed </think>
        a = ANS.findall(thinking)
        if a:
            return a[-1], "answer tag in thinking"
        b = BOXED.findall(thinking)
        if b:
            return " ; ".join(b), "boxed in thinking"
    return None, "missing"


def grade(d, answers, mode="qa", include_thinking=False):
    qmeta = {q["question_id"]: q for q in d["questions"]}
    rub = collections.defaultdict(list)
    for r in d["rubric"]:
        rub[r["question_id"]].append(r)
    rows = []
    for a in answers:
        qid, resp, prompt = a["question_id"], a.get("response", "") or "", a.get("prompt", "")
        q = qmeta.get(qid, {})
        level = int(a.get("level", q.get("level", 0)))
        fin_text, style = split_final(resp, a.get("thinking") or "")
        fin_vals = numbers(fin_text) if fin_text is not None else []
        work = resp + ("\n" + (a.get("thinking") or "") if include_thinking else "")
        all_vals = numbers(work)
        prompt_vals = numbers(prompt)
        qrows = []
        for r in rub[qid]:
            ts = targets(r.get("target"))
            excluded = ""
            if r.get("kind") == "rounding":
                excluded = "rounding not auto-graded"
            elif r.get("kind") == "input" and level >= 3:
                excluded = "input given in data table"
            elif not ts:
                excluded = "no numeric target"
            elif any(t == 0 for t in ts):
                excluded = "zero target not auto-graded"
            elif all(any(abs(v - t) <= max(0.0005 * abs(t), 0.005) for v, _, _ in prompt_vals) for t in ts):
                excluded = "target already in prompt"
            ok = False
            if not excluded:
                pool = fin_vals if r.get("kind") in ("final", "trap", "alternative") else all_vals
                ok = bool(pool) and all(matches(pool, t, r, mode) for t in ts)
            qrows.append(dict(question_id=qid, tier=q.get("tier", "basic"), level=level, item=r.get("item"),
                              kind=r.get("kind"), step=r.get("step"), component=r.get("component"),
                              checkpoint=r.get("checkpoint"), points=int(r.get("points") or 0),
                              earned=0, correct=ok if not excluded else "", excluded=excluded,
                              marker=style, criterion=r.get("criterion")))
        final_ok = any(x["kind"] == "final" and x["correct"] is True for x in qrows)
        for x in qrows:
            if x["kind"] in ("trap", "alternative") and x["correct"] is True and final_ok:
                x["correct"] = False             # a hit only counts when the final answer is wrong
                x["note"] = "matched, but final answer also correct"
            x["earned"] = x["points"] if x["correct"] is True else 0
        rows.extend(qrows)
    return rows


ZERO = ("trap", "alternative")


def summary_lines(rows, answers):
    out = []
    p = out.append
    zero_rows = [r for r in rows if r["kind"] in ZERO]
    rows = [r for r in rows if r["kind"] not in ZERO]
    q = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if not r["excluded"]:
            q[r["question_id"]][0] += r["earned"]; q[r["question_id"]][1] += r["points"]
    pct = [e / t for e, t in q.values() if t]
    p(f"Questions graded: {len(q)}   mean score per question: {100*sum(pct)/max(len(pct),1):.1f}%")
    fin = [r for r in rows if r["kind"] == "final" and not r["excluded"]]
    p(f"Final answers correct: {sum(1 for r in fin if r['correct'] is True)}/{len(fin)}")
    styles = collections.Counter(split_final(a.get("response", "") or "", a.get("thinking") or "")[1] for a in answers)
    p("Final-answer marker: " + ", ".join(f"{k} {v}" for k, v in styles.most_common()) + " (missing = final scored zero)")
    capped = [a["question_id"] for a in answers if a.get("max_new_tokens") and a.get("new_tokens", 0) >= a["max_new_tokens"]]
    unfin = [a["question_id"] for a in answers if a.get("thinking_finished") is False]
    p(f"Hit the token limit: {len(capped)} {capped[:20]}")
    if unfin:
        p(f"Thinking never finished: {len(unfin)} {unfin[:20]}")
    fc = collections.defaultdict(lambda: [0, 0])
    for r in fin:
        fc[(r["tier"], r["level"])][0] += 1 if r["correct"] is True else 0; fc[(r["tier"], r["level"])][1] += 1
    p("\nFinal answers correct by tier and level:")
    for k, (c, n) in sorted(fc.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        p(f"  {k[0]:8s} L{k[1]}  {c:3d}/{n:<3d} = {100*c/n:5.1f}%")
    for kind, label in (("trap", "Fell for the trap (final wrong AND matched the trap value)"),
                        ("alternative", "Used basic shares (final wrong AND matched the basic-share value)")):
        z = [r for r in zero_rows if r["kind"] == kind and not r["excluded"]]
        if z:
            hits = [r["question_id"] for r in z if r["correct"] is True]
            both = [r["question_id"] for r in z if r.get("note")]
            p(f"\n{label}: {len(hits)}/{len(z)}" + (f"   (also matched but final correct, not counted: {len(both)})" if both else ""))
            if hits:
                p("   " + ", ".join(hits))

    def agg(key):
        s = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if r["excluded"]:
                continue
            s[r[key]][0] += r["earned"]; s[r[key]][1] += r["points"]
        return s
    for key in ("tier", "level", "step", "kind"):
        p(f"\nBy {key}:")
        for k, (e, t) in sorted(agg(key).items(), key=lambda x: str(x[0])):
            p(f"  {str(k):40s} {e:4d}/{t:<4d} = {100*e/t if t else 0:5.1f}%")
    ex = collections.Counter(r["excluded"] for r in rows if r["excluded"])
    p("\nExcluded items: " + str(dict(ex)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default="../data/questions/QA_set_v2.json")
    ap.add_argument("--answers", nargs="*", default=[])
    ap.add_argument("--tolerance", choices=["qa", "plan"], default="qa")
    ap.add_argument("--include-thinking", action="store_true")
    ap.add_argument("--out", default="../results/graded")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.qa))
    if a.self_test:
        answers = []
        for q in d["questions"]:
            if int(q["level"]) == 1:
                continue
            fake = "\n".join(r["criterion"] for r in d["rubric"]
                             if r["question_id"] == q["question_id"] and r.get("kind") not in ZERO)
            answers.append(dict(question_id=q["question_id"], level=q["level"], prompt=q["question"],
                                response=fake + "\nFinal Answer: " + str(q["final_answer"])))
        for mode in ("qa", "plan"):
            rows = grade(d, answers, mode)
            bad = [r for r in rows if r["correct"] is False and r["kind"] not in ZERO]
            traps = [r for r in rows if r["kind"] in ZERO and r["correct"] is True]
            print(f"SELF-TEST [{mode}]", "PASSED: perfect answers score 100%" if not bad else f"FAILED on {len(bad)} items",
                  f"| trap/alternative hits on perfect answers: {len(traps)} (must be 0)")
            for r in bad[:10]:
                print("   ", r["question_id"], r["item"], r["criterion"][:80])
        return
    os.makedirs(a.out, exist_ok=True)
    tag = f"ver05_{a.tolerance}" + ("_think" if a.include_thinking else "")
    for path in a.answers:
        opener = gzip.open if path.endswith(".gz") else open
        answers = [json.loads(l) for l in opener(path, "rt") if l.strip()]
        rows = grade(d, answers, a.tolerance, a.include_thinking)
        base = os.path.basename(path)
        base = base[:-3] if base.endswith(".gz") else base
        base = os.path.splitext(base)[0]
        out_csv = os.path.join(a.out, f"graded_{tag}_{base}.csv")
        out_txt = os.path.join(a.out, f"summary_{tag}_{base}.txt")
        if os.path.exists(out_csv) or os.path.exists(out_txt):
            print(f"SKIP {base}: output exists (not overwriting)")
            continue
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
        lines = [f"{base}  [grade_ver05, tolerance={a.tolerance}, include_thinking={a.include_thinking}, qa={os.path.basename(a.qa)}]", ""] \
            + summary_lines(rows, answers)
        open(out_txt, "w").write("\n".join(lines) + "\n")
        print("\n".join(lines[:6])); print("   ->", out_csv)


if __name__ == "__main__":
    main()
