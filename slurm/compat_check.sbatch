#!/bin/bash
# CPU-only check of the V100 environment (vLLM 0.10.1 + transformers 5.19) with run_model.py's patch, for the
# 7 models that run on V100. Fails (exit 1) if a tokenizer or a RoPE config is wrong.
#   sbatch compat_check.sbatch
#SBATCH -J compat
#SBATCH -A <your-allocation>
#SBATCH -p debug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:50:00
#SBATCH -o logs/slurm/compat_check_%j.log
ROOT=${REPO_ROOT:?set REPO_ROOT to this repository}
ENV=${MODEL_STORE:?set MODEL_STORE}/conda-env-v100
export HF_HOME=$MODEL_STORE/hf_home HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PATH="$ENV/bin:$PATH"
cd "$ROOT/pipeline" || exit 1
echo "start $(date) on $(hostname)"
python -u -B compat_check.py qwen25-7b fin-r1 dianjin-7b llama31-8b fino1-8b qwen3-8b fin-o1-8b
rc=$?; echo "exit $rc $(date)"; exit $rc
