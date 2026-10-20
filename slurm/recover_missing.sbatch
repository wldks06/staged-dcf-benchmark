#!/bin/bash
# Run the (tool, seed, question set) batches a model run never wrote, e.g. after a 24-hour time-out
# (Qwen3-8B job 12259599 reached the limit with the seed-2 calculator batches still to go). Reads the answer files
# that exist, builds an --only-map with every question of each missing batch, runs just those, grades them.
#   sbatch [gpu options] --dependency=afterany:<model job> recover_missing.sbatch <preset>
#SBATCH -J recover
#SBATCH -A <your-allocation>
#SBATCH -p v100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=2
#SBATCH --cpus-per-task=16
#SBATCH --mem=160G
#SBATCH --time=24:00:00
#SBATCH -o logs/slurm/recover_%x_%j.log
PRESET=${1:?usage: sbatch recover_missing.sbatch <preset>}; shift
source "$REPO_ROOT/slurm/env.sh" || exit 3
OUT=$ROOT/results/answers/$PRESET
MARK=$(mktemp); sleep 1
cd "$ROOT/pipeline" || exit 1
python - "$PRESET" "$OUT" "$ROOT/data/questions" <<'PY' || exit 1
import glob, json, os, re, sys
preset, out, qdir = sys.argv[1:4]
qa = {"v2": "QA_set_v2.json", "ver03": "QA_set_ver03.json", "ver03_newco": "QA_set_ver03_newco.json"}
reasoning = preset in ("qwen3-8b", "qwen3-14b", "qwen3-32b", "fin-r1", "dianjin-7b", "dianjin-32b", "fin-o1-8b", "fin-o1-14b", "fino1-8b")
seeds = ["0", "1", "2"] if reasoning else ["0"]
have = set()
for f in glob.glob(f"{out}/answers_ver02_*.jsonl*"):
    m = re.search(r"_(calc_)?s(\d+)_(v2|ver03_newco|ver03)_", os.path.basename(f))
    if m:
        have.add(("calc" if m.group(1) else "none", m.group(2), m.group(3)))
maps = {"none": {}, "calc": {}}
for tool in ("none", "calc"):
    for s in seeds:
        for tag, fname in qa.items():
            if (tool, s, tag) not in have:
                ids = [q["question_id"] for q in json.load(open(os.path.join(qdir, fname)))["questions"] if int(q["level"]) >= 2]
                maps[tool].setdefault(tag, {})[s] = ids
for tool in ("none", "calc"):
    json.dump(maps[tool], open(f"{out}/missing_map_{tool}.json", "w"))
    n = sum(len(v) for d in maps[tool].values() for v in d.values())
    print(f"{preset} {tool}: {n} answers missing ->", {k: {s: len(v) for s, v in d.items()} for k, d in maps[tool].items()})
PY
for TOOL in none calc; do
  if [ "$(python -c "import json;print(sum(len(v) for d in json.load(open('$OUT/missing_map_$TOOL.json')).values() for v in d.values()))")" != "0" ]; then
    python -u -B run_model.py --preset "$PRESET" \
      --qa $ROOT/data/questions/QA_set_v2.json,$ROOT/data/questions/QA_set_ver03.json,$ROOT/data/questions/QA_set_ver03_newco.json --levels 2,3,4,5 \
      --tools $TOOL --seeds 0,1,2 --only-map "$OUT/missing_map_$TOOL.json" --tp "$NGPU" --dtype "$DTYPE" --out "$OUT" "$@"
  fi
done
for f in $(find "$OUT" -maxdepth 1 -name 'answers_ver02_*.jsonl' -newer "$MARK" | sort); do
  grade_three_modes "$f" "$ROOT/results/graded/$PRESET"
done
rm -f "$MARK"; echo "recover done $(date)"
