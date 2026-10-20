#!/bin/bash
# Download the twelve models of the paper into $MODEL_STORE/hf_home. CPU only; re-running is safe (finished
# files are skipped). Only safetensors weights, configs and tokenizer files are fetched (no .bin/.pth/.gguf, no
# custom code). The TheFinAI repositories are gated: request access on Hugging Face first and log in once with
# `hf auth login` (the token is stored in $HF_HOME/token, never in this repository).
#   sbatch download_models.sbatch
#SBATCH -J dl_models
#SBATCH -A <your-allocation>
#SBATCH -p general
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=10:00:00
#SBATCH -o logs/slurm/download_models_%j.log

ENV=${MODEL_STORE:?set MODEL_STORE}/conda-env
export HF_HOME=$MODEL_STORE/hf_home
export HF_HUB_DISABLE_TELEMETRY=1
HF="$ENV/bin/hf"
[ -x "$HF" ] || HF="$ENV/bin/huggingface-cli"
echo "Start $(date)  host $(hostname)  cli $HF"

MODELS=(
  Qwen/Qwen2.5-7B-Instruct         # 15.2 GB
  Qwen/Qwen2.5-32B-Instruct        # 65.5 GB
  meta-llama/Llama-3.1-8B-Instruct # 16.1 GB (gated)
  Qwen/Qwen3-8B                    # 16.4 GB
  Qwen/Qwen3-14B                   # 29.5 GB
  Qwen/Qwen3-32B                   # 65.5 GB
  SUFE-AIFLM-Lab/Fin-R1            # 15.2 GB, Qwen2.5-7B-Instruct fine-tune
  DianJin/DianJin-R1-7B            # 15.2 GB, Qwen2.5-7B-Instruct fine-tune
  DianJin/DianJin-R1-32B           # 65.5 GB, Qwen2.5-32B-Instruct fine-tune
  TheFinAI/Fin-o1-8B               # 16.4 GB, Qwen3-8B fine-tune (gated)
  TheFinAI/Fin-o1-14B              # 29.5 GB, Qwen3-14B fine-tune (gated)
  TheFinAI/Fino1-8B                # 16.1 GB, Llama-3.1-8B-Instruct fine-tune (gated)
)

status=()
for m in "${MODELS[@]}"; do
  echo; echo "===== $m  $(date +%H:%M:%S)"
  # one glob per --include / --exclude (several globs after one flag are read as file names)
  if "$HF" download "$m" \
       --include "*.safetensors" --include "*.json" --include "*.txt" --include "*.model" \
       --include "*.jinja" --include "tokenizer*" --include "vocab*" \
       --exclude "*.bin" --exclude "*.pth" --exclude "*.pt" --exclude "*.gguf" --exclude "original/*" --exclude "*.py"; then
    status+=("OK    $m")
  else
    status+=("FAIL  $m")
  fi
done

echo; echo "===== Summary $(date)"
printf '%s\n' "${status[@]}"
for m in "${MODELS[@]}"; do
  d="$HF_HOME/hub/models--${m//\//--}"
  s=$(ls -d "$d"/snapshots/* 2>/dev/null | head -1)
  [ -n "$s" ] && printf '%-40s %8s  %s safetensors\n' "$m" "$(du -shL "$s" | cut -f1)" "$(ls "$s" | grep -c safetensors)"
done
