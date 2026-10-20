#!/bin/bash
# Regrade every answer file (the pilot runs and all model runs) with pipeline/grade.py in the three modes
# (qa, plan, plan + thinking), then build the combined table and the paper tables. CPU only, about 20 minutes.
# grade.py never overwrites, so a graded file that already exists is skipped: to regrade from scratch, point
# GRADED_DIR at an empty folder.
#   sbatch regrade.sbatch                       (or run the same lines on a laptop, see docs/REPRODUCE.md)
#SBATCH -J regrade
#SBATCH -A <your-allocation>
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH -o logs/slurm/regrade_%j.log
ROOT=${REPO_ROOT:?set REPO_ROOT to this repository}
PY=${PY:-python}
STAMP=$(date +%Y%m%d-%H%M)
GRADED=${GRADED_DIR:-$ROOT/results/graded}
cd "$ROOT/pipeline" || exit 1
$PY -B grade.py --qa $ROOT/data/questions/QA_set_v2.json --self-test || exit 1
qa_of() { case "$1" in *_ver03_newco_*) echo $ROOT/data/questions/QA_set_ver03_newco.json;; *_ver03_*) echo $ROOT/data/questions/QA_set_ver03.json;; *) echo $ROOT/data/questions/QA_set_v2.json;; esac; }
for f in $ROOT/results/answers/*/answers_*.jsonl*; do
  [ -f "$f" ] || continue
  m=$(basename $(dirname $f))
  mkdir -p $GRADED/$m
  for MODE in qa plan; do $PY -B grade.py --qa $(qa_of $f) --tolerance $MODE --out $GRADED/$m --answers $f | grep -E "^SKIP|Final answers|marker" ; done
  $PY -B grade.py --qa $(qa_of $f) --tolerance plan --include-thinking --out $GRADED/$m --answers $f | grep -E "^SKIP|Final answers"
done
$PY -B summarize.py --graded $GRADED --out $ROOT/results/summary_$STAMP
$PY -B analyze_paper.py --graded $GRADED --out $ROOT/results/paper_tables_$STAMP
echo "combined table: results/summary_$STAMP/combined.md, paper tables: results/paper_tables_$STAMP/tables_qa.md  $(date)"
