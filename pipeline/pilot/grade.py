"""Grade model answers against the rubric in QA_set_v1.json.

Usage:
    python grade.py --qa QA_set_v1.json --answers answers_<model>_<time>.jsonl
Self-test with perfect answers (should score 100%):
    python grade.py --qa QA_set_v1.json --self-test

How an item is scored (automatic, no AI judge)
- An item earns its points if a number in the reply matches the rubric target within the
  rubric's tolerance (exact = within 0.05 at one-decimal rounding; rel = relative; abs_pp =
  percentage points). Percent targets also accept the decimal form (7.81% or 0.0781).
  Dollar-million targets also accept billions (18.99 billion = 18,990 million).
- "final" items are matched ONLY against the text after the last 'FINAL ANSWER:' line when the reply has
  one (v2 change: v1 also accepted any matching number anywhere in the reply, which let a stray
  intermediate number count as a correct final answer). Replies with no 'FINAL ANSWER:' line fall
  back to the whole reply.
- Not scored: 'rounding' items, Level 3 'input' items (their values are given in the
  data table), zero-valued targets, and any item whose exact target number already
  appears in the prompt.
- Number matching is lenient (any number in the reply within tolerance counts), so treat
  this as a pilot grader and spot-check a few graded answers by hand.
  These are listed as excluded so the report stays honest.
v3 (2026-10-14): trap and alternative items (0 points) are judged on the FINAL ANSWER line only and
reported separately; summary adds tier and final-answer accuracy by tier and level.
Writes graded_v3_<answers-name>.csv (per item) and prints a summary. Reads only; never deletes.
"""
import argparse, json, re, csv, sys, os, collections

NUM = re.compile(r"\(?-?\$?\s*\d[\d,]*\.?\d*\)?\s*(?:%|percent|billion|bn|million|mm|m\b|x\b)?", re.I)

def numbers(text):
    vals = []
    for m in NUM.finditer(text or ""):
        s = m.group(0)
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

def close(v, t, tol_type, tol_value):
    tol_value = float(tol_value or 0)
    if tol_type == "exact":
        return abs(v - t) <= 0.05 + 1e-9
    if tol_type == "rel":
        return abs(v - t) <= abs(t) * tol_value + 1e-9 or (t == 0 and abs(v) < 1e-6)
    if tol_type == "abs_pp":
        return abs(v - t) <= tol_value + 0.005 + 1e-9
    return False

def matches(vals, t, item):
    unit = (item.get("unit") or "").lower()
    for v, is_bn, is_pct in vals:
        cands = [v]
        if unit == "%" and not is_pct:
            cands.append(v * 100)              # 0.0781 -> 7.81
        if "$ millions" in unit and is_bn:
            cands = [v * 1000]                 # 18.99 billion -> 18,990 million
        if any(close(c, t, item.get("tol_type"), item.get("tol_value")) for c in cands):
            return True
    return False

def grade(d, answers):
    tiers = {q["question_id"]: q.get("tier", "basic") for q in d["questions"]}
    rub = collections.defaultdict(list)
    for r in d["rubric"]:
        rub[r["question_id"]].append(r)
    rows = []
    for a in answers:
        qid, resp, prompt = a["question_id"], a.get("response", ""), a.get("prompt", "")
        all_vals = numbers(resp)
        fin = resp.split("FINAL ANSWER:")[-1] if "FINAL ANSWER:" in resp else ""
        fin_vals = numbers(fin)
        prompt_vals = numbers(prompt)
        for r in rub[qid]:
            ts = targets(r.get("target"))
            excluded = ""
            if r.get("kind") == "rounding":
                excluded = "rounding not auto-graded"
            elif r.get("kind") == "input" and int(a.get("level", 0)) == 3:
                excluded = "input given in data table"
            elif not ts:
                excluded = "no numeric target"
            elif any(t == 0 for t in ts):
                excluded = "zero target not auto-graded"
            elif all(any(abs(v - t) <= max(0.0005 * abs(t), 0.005) for v, _, _ in prompt_vals) for t in ts):
                excluded = "target already in prompt"
            ok = False
            if not excluded:
                if r.get("kind") in ("final", "trap", "alternative"):
                    # v2/v3: judged only on the FINAL ANSWER line when present
                    pools = [fin_vals] if "FINAL ANSWER:" in resp else [all_vals]
                else:
                    pools = [all_vals]
                ok = any(all(matches(pool, t, r) for t in ts) for pool in pools if pool)
            rows.append(dict(question_id=qid, tier=tiers.get(qid, "basic"), level=a.get("level"), item=r.get("item"), kind=r.get("kind"),
                             step=r.get("step"), component=r.get("component"), checkpoint=r.get("checkpoint"),
                             points=int(r.get("points") or 0), earned=int(r.get("points") or 0) if ok else 0,
                             correct=ok if not excluded else "", excluded=excluded, criterion=r.get("criterion")))
    return rows

ZERO = ("trap", "alternative")

def summary(rows):
    zero_rows = [r for r in rows if r["kind"] in ZERO]
    rows = [r for r in rows if r["kind"] not in ZERO]
    def agg(key):
        s = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if r["excluded"]:
                continue
            s[r[key]][0] += r["earned"]; s[r[key]][1] += r["points"]
        return s
    q = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if not r["excluded"]:
            q[r["question_id"]][0] += r["earned"]; q[r["question_id"]][1] += r["points"]
    pct = [e / p for e, p in q.values() if p]
    print(f"Questions graded: {len(q)}   mean score per question: {100*sum(pct)/max(len(pct),1):.1f}%")
    fin = [r for r in rows if r["kind"] == "final" and not r["excluded"]]
    print(f"Final answers correct: {sum(1 for r in fin if r['correct'])}/{len(fin)}")
    fc = collections.defaultdict(lambda: [0, 0])
    for r in fin:
        fc[(r["tier"], r["level"])][0] += 1 if r["correct"] else 0; fc[(r["tier"], r["level"])][1] += 1
    print("\nFinal answers correct by tier and level:")
    for k, (c, n) in sorted(fc.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(f"  {k[0]:8s} L{k[1]}  {c:3d}/{n:<3d} = {100*c/n:5.1f}%")
    for kind, label in (("trap", "Fell for the trap (FINAL ANSWER matched the trap value)"),
                        ("alternative", "Matched the basic-share alternative value per share")):
        z = [r for r in zero_rows if r["kind"] == kind and not r["excluded"]]
        if z:
            print(f"\n{label}: {sum(1 for r in z if r['correct'])}/{len(z)}")
            hits = [r["question_id"] for r in z if r["correct"]]
            if hits:
                print("  ", ", ".join(hits))
    for key in ("tier", "level", "step", "kind"):
        print(f"\nBy {key}:")
        for k, (e, p) in sorted(agg(key).items(), key=lambda x: str(x[0])):
            print(f"  {str(k):40s} {e:4d}/{p:<4d} = {100*e/p if p else 0:5.1f}%")
    ex = collections.Counter(r["excluded"] for r in rows if r["excluded"])
    print("\nExcluded items:", dict(ex))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", default="QA_set_v1.json")
    ap.add_argument("--answers")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.qa))
    if a.self_test:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from run_model import build_prompts
        lv = {int(q["level"]) for q in d["questions"]} - {1}
        prompts = {p["question_id"]: p for p in build_prompts(d, lv)}
        answers = []
        for qid, p in prompts.items():
            fake = "\n".join(f"{r['criterion']}" for r in d["rubric"] if r["question_id"] == qid and r.get("kind") not in ("trap", "alternative"))
            final = next((q["final_answer"] for q in d["questions"] if q["question_id"] == qid), "")
            answers.append(dict(p, response=fake + "\nFINAL ANSWER: " + str(final)))
        rows = grade(d, answers)
        summary(rows)
        bad = [r for r in rows if r["correct"] is False and r["kind"] not in ("trap", "alternative")]
        trap_hits = [r for r in rows if r["kind"] == "trap" and r["correct"] is True]
        if trap_hits:
            print("SELF-TEST WARNING: perfect answers matched a trap value:", [r["question_id"] for r in trap_hits])
        print("\nSELF-TEST", "PASSED: perfect answers score 100%." if not bad else f"FAILED on {len(bad)} items:")
        for r in bad[:20]:
            print("  ", r["question_id"], r["item"], r["criterion"])
        return
    answers = [json.loads(l) for l in open(a.answers) if l.strip()]
    rows = grade(d, answers)
    out = "graded_v3_" + os.path.splitext(os.path.basename(a.answers))[0] + ".csv"
    if os.path.exists(out):
        sys.exit(f"{out} already exists. Not overwriting it; rename or move it first.")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summary(rows)
    print("\nPer-item results written to", out)

if __name__ == "__main__":
    main()
