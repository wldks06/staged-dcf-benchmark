#!/bin/bash
# Shared job environment, sourced by every GPU job (run_model.sbatch, rerun_capped.sbatch, recover_missing.sbatch).
# Set before submitting (for example in ~/.bashrc or on the sbatch command line with --export):
#   REPO_ROOT    this repository on the cluster file system
#   MODEL_STORE  where the two conda environments, the Hugging Face cache and the vLLM cache live:
#                  $MODEL_STORE/conda-env       vLLM 0.31.0, torch 2.13 (H100, bfloat16)
#                  $MODEL_STORE/conda-env-v100  vLLM 0.10.1.1, torch 2.7.1, transformers 5.19 (V100, float16)
#                  $MODEL_STORE/hf_home         filled by download_models.sbatch
# What it does:
#  - the conda env is used directly through PATH (batch jobs on our cluster failed at `module load conda`)
#  - Hugging Face runs offline: the models are downloaded beforehand
#  - vLLM >= 0.30 FlashInfer JIT is switched off (the GPU nodes have no nvcc)
#  - every cache lives under $REPO_ROOT/cache: with 2 GPUs vLLM 0.31 imports FlashInfer's all-reduce, which
#    creates ~/.cache/flashinfer, and a broken ~/.cache link killed the first 2xH100 jobs (12259437-12259439)
#  - a GPU probe that cannot hang the job (some nodes had a driver that never answered)
#  - V100 nodes get the vLLM 0.10.1 env and float16 (V100 has no bfloat16)
export REPO_ROOT=${REPO_ROOT:?set REPO_ROOT to this repository}
export MODEL_STORE=${MODEL_STORE:?set MODEL_STORE to the folder with the conda envs and hf_home}
export ROOT=$REPO_ROOT
export HF_HOME="$MODEL_STORE/hf_home" HF_HUB_CACHE="$MODEL_STORE/hf_home/hub"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export VLLM_USE_FLASHINFER_SAMPLER=0 VLLM_USE_FLASHINFER_MOE_FP16=0 VLLM_USE_FLASHINFER_MOE_FP8=0
export VLLM_CACHE_ROOT="$MODEL_STORE/vllm_cache"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export CACHE_ROOT="$ROOT/cache"
export FLASHINFER_WORKSPACE_BASE="$CACHE_ROOT" XDG_CACHE_HOME="$CACHE_ROOT/xdg" TRITON_CACHE_DIR="$CACHE_ROOT/triton"
mkdir -p "$CACHE_ROOT/.cache/flashinfer" "$XDG_CACHE_HOME" "$TRITON_CACHE_DIR"
echo "[env] $(date '+%F %T') host=$(hostname) job=${SLURM_JOB_ID:-interactive} partition=${SLURM_JOB_PARTITION:-?}"

GPUS=""; out=$(mktemp); ( nvidia-smi --query-gpu=name,memory.total --format=csv,noheader >"$out" 2>/dev/null ) </dev/null & p=$!
for _ in $(seq 1 30); do kill -0 $p 2>/dev/null || break; sleep 1; done
if kill -0 $p 2>/dev/null; then kill -9 $p 2>/dev/null; echo "[env] nvidia-smi did not answer in 30 s on $(hostname): GPU driver not responding. Resubmit with --exclude=$(hostname -s)"; exit 3; fi
GPUS=$(cat "$out"); rm -f "$out"
echo "[env] GPUs: $(echo "$GPUS" | paste -sd ';' -)"
export NGPU=$(echo "$GPUS" | grep -c . )

if echo "$GPUS" | grep -q V100; then
  export ENV="$MODEL_STORE/conda-env-v100" DTYPE=float16
else
  export ENV="$MODEL_STORE/conda-env" DTYPE=bfloat16
fi
export PATH="$ENV/bin:$PATH" CONDA_PREFIX="$ENV"
for f in "$ENV"/etc/conda/activate.d/*.sh; do [ -f "$f" ] && source "$f"; done 2>/dev/null
echo "[env] env=$ENV python=$(command -v python) dtype=$DTYPE ngpu=$NGPU"

# The question set each answer file belongs to, from its file name.
qa_of() {
  case "$1" in
    *_ver03_newco_*) echo "$ROOT/data/questions/QA_set_ver03_newco.json" ;;
    *_ver03_*)       echo "$ROOT/data/questions/QA_set_ver03.json" ;;
    *)               echo "$ROOT/data/questions/QA_set_v2.json" ;;
  esac
}
# Grade one answer file in the three modes of the paper (qa = headline, plan = looser, plan + thinking).
grade_three_modes() {   # <answers file> <output folder>
  for MODE in qa plan; do python -B "$ROOT/pipeline/grade.py" --qa "$(qa_of "$1")" --tolerance $MODE --out "$2" --answers "$1" | head -3; done
  python -B "$ROOT/pipeline/grade.py" --qa "$(qa_of "$1")" --tolerance plan --include-thinking --out "$2" --answers "$1" | head -3
}
