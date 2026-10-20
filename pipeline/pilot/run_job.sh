#!/bin/bash
# GPU job: run one open model on the Q&A set (Levels 2 and 3 only).
# Usage:  sbatch run_job.sh <huggingface model name> [extra options for run_model.py]
#   e.g.  sbatch run_job.sh Qwen/Qwen2.5-32B-Instruct
#         sbatch --time=06:00:00 run_job.sh Qwen/Qwen3-32B --thinking --levels 3 --max-new-tokens 24576
# Asks for 1 H100 GPU for at most 3 hours. When the script ends, the GPU is released.
#SBATCH -J qa_run
#SBATCH -A <your-allocation>
#SBATCH -p h100-single
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=03:00:00
#SBATCH -o qa_run_%j.log

# How many questions: 0 = all 24.
LIMIT=0
MODEL="${1:-Qwen/Qwen2.5-7B-Instruct}"
shift   # anything after the model name is passed on to run_model.py
PY=${PY:-python}   # the pilot environment: transformers + torch, no vLLM

cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}" || exit 1   # submit from pipeline/pilot/
export HF_HOME=${HF_HOME:?set HF_HOME to the Hugging Face cache with the models}
export HF_HUB_OFFLINE=1   # use the already-downloaded model; never download during the job
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True   # reduces GPU memory fragmentation on long answers
echo "Model: $MODEL  Extra options: $*"
nvidia-smi
# -u makes progress lines appear in the log immediately
$PY -u -B run_model.py --qa ../../data/questions/QA_set_v1.json --model "$MODEL" --limit $LIMIT --max-new-tokens 4096 "$@"
