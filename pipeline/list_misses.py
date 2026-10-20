"""List the questions a model got wrong (final answer outside tolerance), with the key and the model's final line.

    python list_misses.py --graded ../results/graded/pilot --answers ../results/answers/pilot \
        --config Qwen3-32B_think --mode qa --out ../results/error_analysis/pilot_qwen3-32b_misses.csv

This is the starting list for a manual error analysis such as the one in Section V-B of the paper (in the pilot
run of Qwen3-32B, 16 of the 184 final answers are outside tolerance; the authors classified them by hand).
Files of the same configuration are pooled and, for a question answered twice, the later time stamp wins, as in
analyze_paper.py. --config is the part of the file name between "answers_" and the question-set tag, e.g.
Qwen3-32B_think (pilot) or ver02_qwen3-32b_think_s0 (main runs, seed 0).
"""
import argparse, csv, glob, gzip, json, os, re

STAMP = re.compile(r"\d{8}-\d{6}")


def final_line(text, n=400):
    text = text or ""
    i = max(text.lower().rfind("final answer"), text.lower().rfind("final response"))
    return " ".join((text[i:] if i >= 0 else text[-n:]).split())[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graded", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--mode", default="qa", choices=["qa", "plan", "plan_think"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    latest = {}                                    # question_id -> (stamp, final row, answers stem)
    for f in sorted(glob.glob(os.path.join(a.graded, f"graded_ver05_{a.mode}_answers_{a.config}_*.csv"))):
        stem = os.path.basename(f)[len(f"graded_ver05_{a.mode}_"):-len(".csv")]
        stamp = STAMP.search(stem).group(0)
        for r in csv.DictReader(open(f)):
            if r["kind"] == "final" and (r["question_id"] not in latest or stamp > latest[r["question_id"]][0]):
                latest[r["question_id"]] = (stamp, r, stem)
    texts = {}
    for stem in {v[2] for v in latest.values()}:
        path = next(p for p in (os.path.join(a.answers, stem + ".jsonl.gz"), os.path.join(a.answers, stem + ".jsonl"))
                    if os.path.exists(p))
        opener = gzip.open if path.endswith(".gz") else open
        for l in opener(path, "rt"):
            rec = json.loads(l)
            texts[(stem, rec["question_id"])] = rec.get("response") or ""
    misses = [(qid, r, stem) for qid, (_, r, stem) in sorted(latest.items()) if r["correct"] != "True"]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "tier", "level", "key (rubric criterion)", "marker", "model final line", "answers file"])
        for qid, r, stem in misses:
            w.writerow([qid, r["tier"], r["level"], r["criterion"], r["marker"], final_line(texts.get((stem, qid))), stem])
    print(f"{len(misses)} of {len(latest)} final answers outside tolerance ({a.mode}) -> {a.out}")


if __name__ == "__main__":
    main()
