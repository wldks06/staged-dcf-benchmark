"""List the calculator-setting answers of a finished run that hit the calculator cap, as an --only-map for
run_model.py (slurm/rerun_capped.sbatch reruns them with the 300-call cap).

    python make_capped_map.py ../results/answers/<preset> [cap=60]   -> <run folder>/capped_map.json

Prints how many questions per question set and seed will be rerun."""
import glob, json, os, re, sys
root = sys.argv[1].rstrip("/")
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 60
preset = os.path.basename(root)
out = {}
for f in sorted(glob.glob(f"{root}/answers_ver02_*_calc_*.jsonl")):
    m = re.search(r"_calc_s(\d+)_(v2|ver03_newco|ver03)_", os.path.basename(f))
    if not m:
        continue
    seed, qa_tag = m.group(1), m.group(2)
    for l in open(f):
        r = json.loads(l)
        if r.get("n_calc", 0) >= cap and r.get("max_calc_rounds", cap) <= cap:
            out.setdefault(qa_tag, {}).setdefault(seed, []).append(r["question_id"])
path = f"{root}/capped_map.json"
json.dump(out, open(path, "w"), indent=1)
n = sum(len(v) for d in out.values() for v in d.values())
print(f"{preset}: {n} capped answers ->", {k: {s: len(v) for s, v in d.items()} for k, d in out.items()}, "->", path)
