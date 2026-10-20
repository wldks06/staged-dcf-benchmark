# Cluster job scripts

The Slurm jobs that ran the twelve models of the paper (Section IV-D) on Indiana University's research cluster: 2x V100 32 GB nodes for the 7B and 8B models, 1x H100 80 GB for the 14B models and 2x H100 for the 32B models. The paths and the allocation name are variables, so the scripts can be adapted to another Slurm cluster; the partition names (`v100`, `h100-single`, `h100-multi`, `h100-debug`, `general`, `debug`) are ours.

## Setup

```bash
export REPO_ROOT=/path/to/staged-dcf-benchmark     # this repository on the cluster file system
export MODEL_STORE=/path/to/model_store            # holds conda-env/, conda-env-v100/, hf_home/
cd "$REPO_ROOT" && mkdir -p logs/slurm             # submit from the repository root; logs go to logs/slurm/
```

and replace `<your-allocation>` in the `#SBATCH -A` lines. Two conda environments are expected:

| Environment | GPUs | vLLM | torch | dtype |
|---|---|---|---|---|
| `$MODEL_STORE/conda-env` | H100 | 0.31.0 | 2.13.0 (CUDA 13.0) | bfloat16 |
| `$MODEL_STORE/conda-env-v100` | V100 | 0.10.1.1 | 2.7.1 (CUDA 12.6), transformers 5.19 | float16 |

[`env.sh`](env.sh) picks the environment and dtype from the GPU it finds, so one job script serves both.

## Scripts

| Script | What it does |
|---|---|
| [`env.sh`](env.sh) | Shared environment of every GPU job: offline Hugging Face cache, FlashInfer JIT off, every cache under `$REPO_ROOT/cache`, a GPU probe that cannot hang, the environment and dtype for the GPU type, and the helper that grades an answer file in the three modes |
| [`download_models.sbatch`](download_models.sbatch) | Downloads the twelve models (safetensors, configs and tokenizers only) into `$MODEL_STORE/hf_home`. The Llama and TheFinAI repositories are gated: request access and run `hf auth login` once beforehand |
| [`compat_check.sbatch`](compat_check.sbatch) | CPU-only check that the V100 environment loads the tokenizer and RoPE configuration of each V100 model correctly ([`pipeline/compat_check.py`](../pipeline/compat_check.py)) |
| [`run_model.sbatch`](run_model.sbatch) | One model, all three question sets, both tool settings, all seeds, in one job; then a sanity check and grading |
| [`submit_all.sh`](submit_all.sh) | Submits two smoke tests (3 questions per set), the twelve model jobs held until the smoke test of their GPU type passes, and the regrade after all of them |
| [`rerun_capped.sbatch`](rerun_capped.sbatch) | Reruns, with the 300-call calculator cap, the calculator answers that hit the 60-call cap of the first pass |
| [`recover_missing.sbatch`](recover_missing.sbatch) | Runs the (tool, seed, question set) batches a job never wrote, for example after its 24-hour time limit |
| [`regrade.sbatch`](regrade.sbatch) | Regrades every answer file in the three modes, then writes the combined table and the paper tables (CPU only) |

## Order of the paper's runs

1. `sbatch slurm/download_models.sbatch`, then `sbatch slurm/compat_check.sbatch`
2. `bash slurm/submit_all.sh`
3. `sbatch -p v100 --gpus-per-node=2 slurm/rerun_capped.sbatch <preset>` for qwen25-7b, llama31-8b, qwen3-8b and qwen3-14b, whose first pass ran with the 60-call cap (with the current default of 300 this step is not needed)
4. `sbatch --dependency=afterany:<job> slurm/recover_missing.sbatch qwen3-8b` (its job reached the 24-hour limit)
5. `sbatch slurm/regrade.sbatch`

What actually ran, job by job, including the failed attempts and their fixes, is in [`logs/README.md`](../logs/README.md). The log names there carry the internal script versions (`run_ver03_...`, `regrade_ver05_...`); [`docs/PIPELINE.md`](../docs/PIPELINE.md) maps them to the scripts here.
