#!/bin/bash
# Rerun, with the 300-call calculator cap, the calculator-setting answers of a finished run that hit the first
# pass's 60-call cap (see pipeline/run_model.py). Same seeds, same file names (new time stamp), so
# analyze_paper.py takes the rerun answer for each of those questions. Then grades the new files.
#   sbatch [gpu options] rerun_capped.sbatch <preset>
#SBATCH -J rerun_cap
#SBATCH -A <your-allocation>
#SBATCH -p h100-single
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH -o logs/slurm/rerun_capped_%x_%j.log
PRESET=${1:?usage: sbatch rerun_capped.sbatch <preset>}; shift
source "$REPO_ROOT/slurm/env.sh" || exit 3
OUT=$ROOT/results/answers/$PRESET
MARK=$(mktemp); sleep 1
cd "$ROOT/pipeline" || exit 1
python -B make_capped_map.py "$OUT" 60 || exit 1
python -u -B run_model.py --preset "$PRESET" \
  --qa $ROOT/data/questions/QA_set_v2.json,$ROOT/data/questions/QA_set_ver03.json,$ROOT/data/questions/QA_set_ver03_newco.json --levels 2,3,4,5 \
  --tools calc --seeds 0,1,2 --only-map "$OUT/capped_map.json" --max-calc-rounds 300 --tp "$NGPU" --dtype "$DTYPE" --out "$OUT" "$@"
rc=$?
for f in $(find "$OUT" -maxdepth 1 -name 'answers_ver02_*.jsonl' -newer "$MARK" | sort); do
  grade_three_modes "$f" "$ROOT/results/graded/$PRESET"
done
rm -f "$MARK"; echo "rerun_capped exit code $rc $(date)"; exit $rc
