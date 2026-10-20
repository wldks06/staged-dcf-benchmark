"""Paper tables from the graded files (graded_ver05_*.csv under results/graded/<preset>/).

    python analyze_paper.py --graded ../results/graded --out ../results/paper_tables

For every (grading mode, model preset, tool, seed) the answer files are pooled across the question sets (v2,
ver03, ver03_newco) and, when a question was answered twice for the same setting (capped reruns), the later
time stamp wins, as in summarize.py. Then, per setting:
  - final-answer accuracy by question group (single calculation, trap, Half A, Half B, full textbook, full
    practitioner, and the same groups at the 2019, 2022 and new-company 2025 dates), on the v2 set (184) and on
    all 308 evaluated questions                                            (paper, Table II and Section V-A)
  - rubric score (points earned over points possible, excluded items left out)
  - step scores on the full textbook valuations (middle and step items by DCF step)          (Section V-B)
  - chain gap: firms whose Half A and Half B are both correct but whose full textbook valuation is not,
    per date set                                                                             (Section V-A)
  - trap falls (trap items matched while the final answer was wrong)
Seeds of the same model and tool are then summarised as mean +/- sd and as pooled counts.
Writes tables_<mode>.md and per_seed_<mode>.csv for each grading mode found; tables_qa.md is the headline.
"""
import argparse, collections, csv, glob, os, re, statistics

PAT = re.compile(r"graded_ver05_(qa|plan|plan_think)_answers_(?:ver02_)?(.+)\.csv$")
GROUP = {("basic", 2): "single", ("trap", 2): "trap", ("half", 4): "halfA", ("half", 5): "halfB",
         ("basic", 3): "full_tb", ("complex", 3): "full_pr"}
V2_GROUPS = ["single", "trap", "halfA", "halfB", "full_tb", "full_pr"]
DATE_GROUPS = ["full_tb@2019", "full_pr@2019", "halfA@2019", "halfB@2019",
               "full_tb@2022", "full_pr@2022", "halfA@2022", "halfB@2022",
               "full_tb@2025n", "full_pr@2025n", "halfA@2025n", "halfB@2025n"]
STEPS = ["Step 2. Project the future", "Step 3. Compute free cash flow", "Step 4. Discount to today",
         "Step 5. Value and decide"]


def parse(fname):
    m = PAT.match(os.path.basename(fname))
    if not m:
        return None
    toks = m.group(2).split("_")
    stamp = next((t for t in toks if re.match(r"^\d{8}-\d{6}$", t)), "")
    qa = "v2"
    if "ver03" in toks:
        qa = "newco" if "newco" in toks else "ver03"
    seed = next((t[1:] for t in toks if re.match(r"^s\d$", t)), "0")
    return dict(mode=m.group(1), preset=toks[0], tool="calc" if "calc" in toks else "none", seed=seed,
                qa=qa, stamp=stamp)


def group_of(row, qa):
    tier, level = row["tier"], int(row["level"])
    if "@" in tier:
        base, year = tier.split("@")
        g = GROUP.get((base, level))
        if qa == "newco":
            year = "2025n"
        return f"{g}@{year}" if g else None
    return GROUP.get((tier, level))


def load(graded):
    """-> {(mode, preset, tool, seed): {qa: {question_id: (stamp, rows)}}}"""
    runs = collections.defaultdict(lambda: collections.defaultdict(dict))
    for f in sorted(glob.glob(os.path.join(graded, "*", "graded_ver05_*.csv"))):
        p = parse(f)
        if not p:
            continue
        key = (p["mode"], p["preset"], p["tool"], p["seed"])
        by_q = collections.defaultdict(list)
        for r in csv.DictReader(open(f)):
            by_q[r["question_id"]].append(r)
        store = runs[key][p["qa"]]
        for qid, rows in by_q.items():
            if qid not in store or p["stamp"] > store[qid][0]:
                store[qid] = (p["stamp"], rows)
    return runs


def metrics(per_qa):
    m = collections.OrderedDict()
    acc = collections.defaultdict(lambda: [0, 0])          # group -> [correct, n]
    rub = collections.defaultdict(lambda: [0.0, 0.0])      # scope -> [earned, points]
    step = collections.defaultdict(lambda: [0.0, 0.0])     # (scope, step) -> [earned, points]
    halves = collections.defaultdict(dict)                 # (qa, ticker) -> {group: correct}
    trap = [0, 0]
    n_all = n_v2 = c_all = c_v2 = 0
    for qa, store in per_qa.items():
        for qid, (stamp, rows) in store.items():
            g = group_of(rows[0], qa)
            if g is None:
                continue
            fin = any(r["kind"] == "final" and r["correct"] == "True" for r in rows)
            acc[g][0] += fin; acc[g][1] += 1
            n_all += 1; c_all += fin
            if qa == "v2":
                n_v2 += 1; c_v2 += fin
            for r in rows:
                pts = float(r["points"] or 0)
                if r["excluded"] or pts <= 0:
                    if r["kind"] == "trap" and not r["excluded"]:
                        trap[1] += 1; trap[0] += r["correct"] == "True"
                    continue
                e = float(r["earned"] or 0)
                rub["all"][0] += e; rub["all"][1] += pts
                if qa == "v2":
                    rub["v2"][0] += e; rub["v2"][1] += pts
                if g.startswith("full_tb") and r["kind"] in ("middle", "step"):
                    step[(g, r["step"])][0] += e; step[(g, r["step"])][1] += pts
            base = g.split("@")[0]
            if base in ("halfA", "halfB", "full_tb"):
                halves[(qa, g.split("@")[1] if "@" in g else "2025", qid.split("-")[0])][base] = fin
    gaps = collections.defaultdict(lambda: [0, 0, 0])      # date set -> [firms with both halves, both ok, both ok but full wrong]
    for (qa, year, ticker), d in halves.items():
        if "halfA" in d and "halfB" in d and "full_tb" in d:
            k = f"{qa}@{year}"
            gaps[k][0] += 1
            if d["halfA"] and d["halfB"]:
                gaps[k][1] += 1
                gaps[k][2] += not d["full_tb"]
    m["n_v2"], m["c_v2"], m["n_all"], m["c_all"] = n_v2, c_v2, n_all, c_all
    m["acc"] = dict(acc); m["rub"] = dict(rub); m["step"] = dict(step); m["gaps"] = dict(gaps); m["trap"] = trap
    return m


def pct(c, n):
    return f"{100.0 * c / n:.1f}" if n else ""


def frac(c, n):
    return f"{c}/{n}" if n else ""


def mean_sd(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return ""
    if len(vals) == 1:
        return f"{vals[0]:.1f}"
    return f"{statistics.mean(vals):.1f} +/- {statistics.stdev(vals):.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graded", default="../results/graded")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    runs = load(a.graded)
    by_mode = collections.defaultdict(list)
    for key, per_qa in runs.items():
        by_mode[key[0]].append((key, metrics(per_qa)))

    for mode, items in by_mode.items():
        items.sort(key=lambda t: t[0])
        # per-seed csv
        groups = V2_GROUPS + DATE_GROUPS
        with open(os.path.join(a.out, f"per_seed_{mode}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["preset", "tool", "seed", "n_v2", "acc_v2", "n_all", "acc_all", "rubric_v2", "rubric_all"]
                       + groups + [f"step_{s[:6].replace(' ', '').replace('.', '')}" for s in STEPS]
                       + ["gap_firms", "gap_both_ok", "gap_full_wrong", "trap_falls", "trap_items"])
            for (_, preset, tool, seed), m in items:
                g = [frac(*m["acc"].get(x, (0, 0))) for x in groups]
                st = [pct(*m["step"].get(("full_tb", s), (0, 0))) for s in STEPS]
                gp = [sum(v[i] for v in m["gaps"].values()) for i in range(3)]
                w.writerow([preset, tool, seed, m["n_v2"], pct(m["c_v2"], m["n_v2"]), m["n_all"], pct(m["c_all"], m["n_all"]),
                            pct(*m["rub"].get("v2", (0, 0))), pct(*m["rub"].get("all", (0, 0)))] + g + st + gp + m["trap"])

        # summary across seeds
        agg = collections.OrderedDict()
        for (_, preset, tool, seed), m in items:
            agg.setdefault((preset, tool), []).append(m)
        lines = [f"# Paper tables, grading mode `{mode}`", "",
                 "Accuracy = final answer within tolerance. Mean +/- sd over seeds where a model was sampled three times; "
                 "cells with a slash are pooled counts over seeds. Groups: single = one calculation (v2 basic L2, 56), "
                 "trap (40), Half A (steps 2-3, 20), Half B (steps 4-5, 20), full textbook (28), full practitioner (20); "
                 "@2019 and @2022 are the same question types for 13 firms at those valuation dates, @2025n for 5 "
                 "firms not in v2.", ""]
        lines += ["## A. Accuracy by model and tool", "",
                  "| model | tool | seeds | v2 acc (184) | all acc (308) | rubric v2 | single | trap | Half A | Half B | full tb | full pr | full tb @2019 | full tb @2022 | full tb @2025n | full pr @2019 | full pr @2022 |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for (preset, tool), ms in agg.items():
            def pooled(x):
                c = sum(m["acc"].get(x, (0, 0))[0] for m in ms); n = sum(m["acc"].get(x, (0, 0))[1] for m in ms)
                return f"{frac(c, n)} ({pct(c, n)})" if n else ""
            lines.append("| " + " | ".join([
                preset, tool, str(len(ms)),
                mean_sd([100.0 * m["c_v2"] / m["n_v2"] if m["n_v2"] else None for m in ms]),
                mean_sd([100.0 * m["c_all"] / m["n_all"] if m["n_all"] else None for m in ms]),
                mean_sd([100.0 * m["rub"]["v2"][0] / m["rub"]["v2"][1] if m["rub"].get("v2") else None for m in ms]),
                pooled("single"), pooled("trap"), pooled("halfA"), pooled("halfB"), pooled("full_tb"), pooled("full_pr"),
                pooled("full_tb@2019"), pooled("full_tb@2022"), pooled("full_tb@2025n"), pooled("full_pr@2019"), pooled("full_pr@2022")]) + " |")
        lines += ["", "## B. Step scores on the v2 full textbook valuations (rubric points earned, %)", "",
                  "| model | tool | " + " | ".join(s.split(". ")[0] for s in STEPS) + " | final (28) |",
                  "|---|---|" + "---|" * (len(STEPS) + 1)]
        for (preset, tool), ms in agg.items():
            cells = []
            for s in STEPS:
                e = sum(m["step"].get(("full_tb", s), (0, 0))[0] for m in ms); p = sum(m["step"].get(("full_tb", s), (0, 0))[1] for m in ms)
                cells.append(pct(e, p))
            c = sum(m["acc"].get("full_tb", (0, 0))[0] for m in ms); n = sum(m["acc"].get("full_tb", (0, 0))[1] for m in ms)
            lines.append(f"| {preset} | {tool} | " + " | ".join(cells) + f" | {frac(c, n)} |")
        lines += ["", "## C. Chain gap and trap falls (pooled over seeds)", "",
                  "Chain gap cells: firms with both halves correct / firms with both halves and a full valuation, then "
                  "how many of those firms still failed the full textbook valuation.", "",
                  "| model | tool | v2 2025 (20 firms) | 2019 (13) | 2022 (13) | new 2025 (5) | trap falls |",
                  "|---|---|---|---|---|---|---|"]
        for (preset, tool), ms in agg.items():
            cells = []
            for k in ["v2@2025", "ver03@2019", "ver03@2022", "newco@2025n"]:
                v = [sum(m["gaps"].get(k, (0, 0, 0))[i] for m in ms) for i in range(3)]
                cells.append(f"{v[1]}/{v[0]} both ok, {v[2]} full wrong" if v[0] else "")
            tf = [sum(m["trap"][i] for m in ms) for i in range(2)]
            lines.append(f"| {preset} | {tool} | " + " | ".join(cells) + f" | {frac(*tf)} |")
        open(os.path.join(a.out, f"tables_{mode}.md"), "w").write("\n".join(lines) + "\n")
        print(f"wrote {a.out}/tables_{mode}.md ({len(agg)} model x tool rows, {len(items)} runs)")


if __name__ == "__main__":
    main()
