#!/bin/bash
# One model, all three question sets, both tool settings, all seeds, in ONE job (the model loads once), then grading.
#   sbatch [partition/GPU options] run_model.sbatch <preset> [extra options for pipeline/run_model.py]
# The partition and GPU count are chosen at submission (see submit_all.sh), e.g.
#   sbatch -p v100 --gpus-per-node=2 run_model.sbatch fin-r1
#   sbatch -p h100-multi --gpus-per-node=2 --mem=240G run_model.sbatch qwen3-32b
# Tensor parallel size = number of GPUs in the job. Answers: results/answers/<preset>/,
# graded files: results/graded/<preset>/. Nothing is overwritten.
#SBATCH -J dcf_run
#SBATCH -A <your-allocation>
#SBATCH -p h100-single
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=10:00:00
#SBATCH -o logs/slurm/run_%x_%j.log

PRESET=${1:?usage: sbatch run_model.sbatch <preset> [options]}; shift
source "$REPO_ROOT/slurm/env.sh" || exit 3
QA_FILES=${QA_FILES:-$ROOT/data/questions/QA_set_v2.json,$ROOT/data/questions/QA_set_ver03.json,$ROOT/data/questions/QA_set_ver03_newco.json}
SEEDS=${SEEDS:-0,1,2}
TOOLS=${TOOLS:-none,calc}
OUT=${OUT_DIR:-$ROOT/results/answers/$PRESET}
GRADED=${GRADED_DIR:-$ROOT/results/graded/$PRESET}
mkdir -p "$OUT" "$GRADED"
MARK=$(mktemp); sleep 1
cd "$ROOT/pipeline" || exit 1
python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda', torch.cuda.is_available())" || exit 1

python -u -B run_model.py --preset "$PRESET" --qa "$QA_FILES" --levels 2,3,4,5 \
  --tools "$TOOLS" --seeds "$SEEDS" --tp "$NGPU" --dtype "$DTYPE" --out "$OUT" "$@"
rc=$?
# sanity: the job must have written answers, and most answers that FINISHED (not cut by the token limit)
# must contain a FINAL ANSWER line. Answers cut by the token limit are not counted (a thinking model in a
# smoke test with a small budget is cut often, which is not a pipeline failure).
python - "$OUT" "$MARK" <<'PY' || rc=4
import glob, json, os, sys, re
out, mark = sys.argv[1], os.path.getmtime(sys.argv[2])
files = [f for f in glob.glob(os.path.join(out, "answers_ver02_*.jsonl")) if os.path.getmtime(f) >= mark]
recs = [json.loads(l) for f in files for l in open(f) if l.strip()]
done = [r for r in recs if r.get("finish_reason") != "length"]
ok = sum(1 for r in done if re.search(r"final\s+answer\s*:", r.get("response") or "", re.I))
calls = sum(r.get("n_calc", 0) for r in recs)
print(f"[sanity] {len(files)} answer files, {len(recs)} answers, {len(recs) - len(done)} cut by the token limit, "
      f"{ok} of {len(done)} finished answers with a FINAL ANSWER line, {calls} calculator calls")
sys.exit(0 if done and ok >= 0.5 * len(done) else 1)
PY

# grade what this job wrote: answers_ver02_* newer than the start marker, each against its own question set
for f in $(find "$OUT" -maxdepth 1 -name 'answers_ver02_*.jsonl' -newer "$MARK" | sort); do
  grade_three_modes "$f" "$GRADED"
done
rm -f "$MARK"
echo "run_model exit code $rc  $(date)"
exit $rc
