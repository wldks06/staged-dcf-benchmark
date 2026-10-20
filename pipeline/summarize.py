"""Combine graded_ver0N_*.csv files into one table per grading mode (accuracy, rubric score, tokens, markers).

Files of the same model and settings are pooled across question sets, levels and shards, e.g. the pilot's
Qwen3-32B runs answers_Qwen3-32B_think_L2_..., _L3_..., _v2_L2_..., _v2_L3_S1of2_... all become one row
"Qwen3-32B_think". When a question was answered twice for the same setting, the file with the later time
stamp wins (and the duplicate is reported).

    python summarize.py --graded ../results/graded --out ../results/summary
"""
import argparse, collections, csv, glob, os, re

DROP = re.compile(r"^(v\d+|ver0[3-9]|newco|L\d+|S\d+of\d+|\d{8}-\d{6}|QA|set|only\w*)$")


def config_of(fname):
    m = re.match(r"graded_ver0\d_(qa|plan)(_think)?_answers_(.+)\.csv$", os.path.basename(fname))
    if not m:
        return None, None, None
    mode = m.group(1) + (m.group(2) or "")
    toks = m.group(3).split("_")
    stamp = next((t for t in toks if re.match(r"^\d{8}-\d{6}$", t)), "")
    key = "_".join(t for t in toks if not DROP.match(t))
    return mode, key, stamp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graded", default="../results/graded")
    ap.add_argument("--out", default="../results/summary")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    groups = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(a.graded, "**", "graded_ver0*_*.csv"), recursive=True)):
        mode, key, stamp = config_of(f)
        if mode:
            groups[(mode, key)].append((stamp, f))

    table, notes = [], []
    for (mode, key), files in sorted(groups.items()):
        by_q = {}
        for stamp, f in sorted(files):                      # later stamp overwrites
            rows = list(csv.DictReader(open(f)))
            qids = {r["question_id"] for r in rows}
            dup = qids & set(by_q)
            if dup:
                notes.append(f"{mode} {key}: {len(dup)} questions answered again in {os.path.basename(f)}; later file kept")
            for qid in qids:
                by_q[qid] = [r for r in rows if r["question_id"] == qid]
        rows = [r for rs in by_q.values() for r in rs]
        fin = [r for r in rows if r["kind"] == "final" and not r["excluded"]]
        ok = lambda r: r["correct"] == "True"
        cell = collections.defaultdict(lambda: [0, 0])
        for r in fin:
            cell[f"{r['tier']} L{r['level']}"][0] += ok(r); cell[f"{r['tier']} L{r['level']}"][1] += 1
        scored = [r for r in rows if r["kind"] in ("final", "middle", "step") and not r["excluded"]]
        pts = sum(int(r["earned"]) for r in scored), sum(int(r["points"]) for r in scored)
        traps = [r for r in rows if r["kind"] == "trap" and not r["excluded"]]
        alts = [r for r in rows if r["kind"] == "alternative" and not r["excluded"]]
        rec = dict(mode=mode, config=key, questions=len(by_q),
                   final_correct=f"{sum(ok(r) for r in fin)}/{len(fin)}",
                   final_pct=round(100 * sum(ok(r) for r in fin) / max(len(fin), 1), 1),
                   rubric_pct=round(100 * pts[0] / max(pts[1], 1), 1),
                   fell_for_trap=f"{sum(ok(r) for r in traps)}/{len(traps)}",
                   used_basic_shares=f"{sum(ok(r) for r in alts)}/{len(alts)}")
        for k in sorted(cell):
            c, n = cell[k]
            rec[k] = f"{c}/{n}"
        table.append(rec)

    # mean and spread over seeds: rows whose config differs only in _s<k>
    seeded = collections.defaultdict(list)
    for r in table:
        m = re.match(r"^(.*)_s(\d+)(_.*)?$", r["config"])
        if m:
            seeded[(r["mode"], m.group(1) + (m.group(3) or ""))].append(r)
    for (mode, base), rows in sorted(seeded.items()):
        if len(rows) < 2:
            continue
        vals = [r["final_pct"] for r in rows]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
        table.append(dict(mode=mode, config=f"{base} (mean of {len(rows)} seeds)", questions=rows[0]["questions"],
                          final_correct="", final_pct=f"{mu:.1f} +/- {sd:.1f}",
                          rubric_pct=round(sum(r["rubric_pct"] for r in rows) / len(rows), 1)))
    keys = []
    for r in table:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(a.out, "combined.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(table)
    md = ["# Combined results", "",
          "Modes: `qa` = rubric tolerances; `plan` = the looser sensitivity tolerances (grade.py); `_think` = thinking text counted for middle/step items.",
          "Cells are final answers correct / graded. `fell_for_trap` and `used_basic_shares` count only answers whose final was wrong.", "",
          "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for r in table:
        md.append("| " + " | ".join(str(r.get(k, "")) for k in keys) + " |")
    if notes:
        md += ["", "Notes:"] + [f"- {n}" for n in notes]
    open(os.path.join(a.out, "combined.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
