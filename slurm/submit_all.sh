#!/bin/bash
# Submit every model run of the paper, from the repository root on the cluster login node:
#   export REPO_ROOT=$PWD MODEL_STORE=/path/to/model_store
#   bash slurm/submit_all.sh
# 1) two smoke tests (3 questions per question set, one seed, with and without the calculator):
#      1 H100 (vLLM 0.31, bfloat16)  and  2 V100 (vLLM 0.10.1, float16)
# 2) the twelve model jobs, each held until the smoke test of its GPU type succeeds (afterok).
#    If a smoke test fails, its model jobs stay pending with DependencyNeverSatisfied:
#    fix the cause, then `scancel` them and run this script again.
# 3) the regrade and the paper tables, after all model jobs.
# Afterwards: rerun_capped.sbatch for any calculator answer that hit an older 60-call cap (not needed with
# the default cap of 300) and recover_missing.sbatch for a job that ran out of time.
# Pairs that are compared run on the same GPU type and vLLM version, so a difference between a fine-tune and
# its base is the fine-tune, not the hardware:
#    V100 x2 : qwen25-7b vs fin-r1 vs dianjin-7b | llama31-8b vs fino1-8b | qwen3-8b vs fin-o1-8b
#    H100 x1 : qwen3-14b vs fin-o1-14b
#    H100 x2 : qwen25-32b vs dianjin-32b | qwen3-32b
# Partition names (v100, h100-single, h100-multi, h100-debug, general) are those of our cluster: adapt them.
set -e
: "${REPO_ROOT:?export REPO_ROOT=<this repository>}" "${MODEL_STORE:?export MODEL_STORE=<model store>}"
cd "$REPO_ROOT"; mkdir -p logs/slurm
S=slurm
SMOKE=$REPO_ROOT/results/smoke
SH=$(OUT_DIR=$SMOKE/h100 GRADED_DIR=$SMOKE/h100/graded SEEDS=0 sbatch --parsable -J smoke_h100 -p h100-debug --gpus-per-node=1 --mem=96G --time=00:55:00 \
     $S/run_model.sbatch qwen3-8b --limit 3 --max-new-tokens 8192 --label smoke)
SV=$(OUT_DIR=$SMOKE/v100 GRADED_DIR=$SMOKE/v100/graded SEEDS=0 sbatch --parsable -J smoke_v100 -p v100 --gpus-per-node=2 --mem=96G --time=01:00:00 \
     $S/run_model.sbatch qwen25-7b --limit 3 --max-new-tokens 8192 --label smoke)
echo "smoke tests: h100 $SH  v100 $SV"

DEPS=""
for m in qwen25-7b fin-r1 dianjin-7b llama31-8b fino1-8b qwen3-8b fin-o1-8b; do
  j=$(sbatch --parsable -J run_$m --dependency=afterok:$SV -p v100 --gpus-per-node=2 --cpus-per-task=16 --mem=160G --time=24:00:00 \
      $S/run_model.sbatch $m)
  echo "v100x2   $m  job $j"; DEPS="$DEPS:$j"
done
for m in qwen3-14b fin-o1-14b; do
  j=$(sbatch --parsable -J run_$m --dependency=afterok:$SH -p h100-single --gpus-per-node=1 --cpus-per-task=16 --mem=160G --time=16:00:00 \
      $S/run_model.sbatch $m)
  echo "h100x1   $m  job $j"; DEPS="$DEPS:$j"
done
for m in qwen25-32b dianjin-32b qwen3-32b; do
  j=$(sbatch --parsable -J run_$m --dependency=afterok:$SH -p h100-multi --gpus-per-node=2 --cpus-per-task=32 --mem=240G --time=24:00:00 \
      $S/run_model.sbatch $m)
  echo "h100x2   $m  job $j"; DEPS="$DEPS:$j"
done
R=$(sbatch --parsable --dependency=afterany$DEPS $S/regrade.sbatch)
echo "regrade and paper tables after all model jobs: $R"
squeue -u $USER -o "%.10i %.12P %.16j %.2t %.10M %.12l %R"
