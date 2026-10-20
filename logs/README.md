# Logs

The Slurm log of every job behind the paper's results, from the pilot (October 13-14, 2026) to the final regrade (October 16, 2026), including the attempts that failed and what fixed them. Times are U.S. Eastern.

The logs are kept as written, with one edit: the cluster paths were replaced by `$REPO_ROOT` (the project folder), `$MODEL_STORE` (the conda environments and model cache) and `$HOME`. They also name the scripts and folders by their internal versions at the time; this table maps them to this repository:

| In the logs | In this repository |
|---|---|
| `code/run_model_ver02.py`, `code/run_model_ver03.py` | [`pipeline/run_model.py`](../pipeline/run_model.py) (version 3; version 2 lacked only the V100 patches and had a 60-call calculator cap) |
| `code/grade_ver04.py` (graded the runs as they finished), `code/grade_ver05.py` | [`pipeline/grade.py`](../pipeline/grade.py) (version 5, which regraded every answer for the paper) |
| `code/summarize_ver01.py`, `code/summarize_ver02.py`, `code/analyze_paper_ver01.py` | [`pipeline/summarize.py`](../pipeline/summarize.py), [`pipeline/analyze_paper.py`](../pipeline/analyze_paper.py) |
| `code/compat_check_ver03.py`, `code/make_capped_map_ver03.py` | [`pipeline/compat_check.py`](../pipeline/compat_check.py), [`pipeline/make_capped_map.py`](../pipeline/make_capped_map.py) |
| `slurm/*_ver02.*`, `slurm/*_ver03.*`, `slurm/regrade_ver05.sbatch` | [`slurm/`](../slurm/) |
| `data/QA_set_*.json` | [`data/questions/`](../data/questions/) |
| `results/ver02_runs/<preset>/` | [`results/answers/<preset>/`](../results/answers/) (answers) |
| `results/ver05_regrade/<preset>/`, `results/ver05_regrade/hawon_ver01/` | [`results/graded/<preset>/`](../results/graded/), [`results/graded/pilot/`](../results/graded/pilot/) |
| `results/ver05_regrade/paper_20261016-1951/`, `combined_20261016-1919/` | [`results/paper_tables/`](../results/paper_tables/), [`results/summary/`](../results/summary/) |
| `qa_run/` (the pilot's working folder) | [`pipeline/pilot/`](../pipeline/pilot/), [`results/answers/pilot/`](../results/answers/pilot/) |

## Pilot ([`pilot/`](pilot/))

| Log | Model | Questions | Answer file |
|---|---|---|---|
| `qa_pilot_12243742.log` | Qwen2.5-7B-Instruct | v1, Levels 2-3 | `answers_Qwen2.5-7B-Instruct_20261013-205733` |
| `qa_run_12244706.log` | Qwen2.5-32B-Instruct | v1, Levels 2-3 | `answers_Qwen2.5-32B-Instruct_20261013-224042` |
| `qa_run_12246248.log` | Qwen3-32B, thinking | v1, Level 3 | `answers_Qwen3-32B_think_L3_20261013-234908` (the Fig. 1 answer) |
| `qa_run_12246249.log` | Qwen3-32B, thinking | v1, Level 2 | `answers_Qwen3-32B_think_L2_20261013-234952` |
| `qa_run_12248338.log`, `qa_run_12248342.log` | Qwen3-32B, thinking | v2 without v1, Level 3, two shards | `answers_Qwen3-32B_think_v2_L3_S1of2_...`, `_S2of2_...` |
| `qa_run_12248343.log` | Qwen3-32B, thinking | v2 without v1, Level 2 | `answers_Qwen3-32B_think_v2_L2_20261014-030812` |
| `qa_run_12248351.log` | Qwen3-32B, thinking | v2 without v1, Levels 4-5 | `answers_Qwen3-32B_think_v2_L45_20261014-030827` |
| `qa_run_12248353.log` | Qwen2.5-7B-Instruct | v2 without v1, Levels 2-5 | `answers_Qwen2.5-7B-Instruct_v2_L2345_20261014-062344` |
| `qa_run_12248354.log` | Qwen2.5-32B-Instruct | v2 without v1, Levels 2-5 | `answers_Qwen2.5-32B-Instruct_v2_L2345_20261014-064230` |

## Main runs ([`slurm/`](slurm/))

### Setup and checks

| Log | Job | Outcome |
|---|---|---|
| `download_models_ver02_12257533.log` | model download | the six financial fine-tunes and the two Qwen2.5 bases downloaded; the Qwen3 and Llama models were already in the cache |
| `compat_check_ver03_12259555.log` | V100 environment check | found that vLLM 0.10.1 under transformers 5 would read the wrong RoPE base for Llama-3.1 and Fino1 without any error; led to the RoPE patch in `run_model.py` |
| `compat_check_ver03_12259584.log` | the same check with the patch | passes for all seven V100 models |
| `run_ver02_smoke_v100_12259427.log` | V100 smoke test, runner version 2 | crashed before generating: `all_special_tokens_extended` missing under transformers 5; led to the tokenizer patch |
| `run_ver02_smoke_h100_12259426.log` | H100 smoke test | loading, generation, 64 calculator calls and grading worked; marked failed only because its sanity rule counted answers cut by the 3,000-token test budget (rule fixed) |
| `run_ver03_smoke3_v100_12259593.log` | V100 smoke test, version 3 | failed in vLLM's custom all-reduce kernel (PCIe V100s without peer-to-peer access); custom all-reduce switched off |
| `run_ver03_smoke3_v100_12259627.log` | V100 smoke test | failed compiling the Triton prefix-prefill kernel on sm_70; prefix caching and chunked prefill switched off on vLLM 0.10 |
| `run_ver03_smoke3_v100_12259671.log` | V100 smoke test | passed |

### Model runs

| Log | Model | GPUs | Outcome |
|---|---|---|---|
| `run_ver03_v3_qwen25-7b_12259594.log` | Qwen2.5-7B-Instruct | 2x V100 | complete |
| `run_ver03_v3_llama31-8b_12259597.log` | Llama-3.1-8B-Instruct | 2x V100 | complete |
| `run_ver03_v3_fin-r1_12259595.log` | Fin-R1 | 2x V100 | complete |
| `run_ver03_v3_dianjin-7b_12259596.log` | DianJin-R1-7B | 2x V100 | complete; exit code 4 only because the sanity check counts `FINAL ANSWER:` lines, which this fine-tune does not write (the grader reads its own markers) |
| `run_ver03_v3_fino1-8b_12259598.log` | Fino1-8B | 2x V100 | complete; exit code 4 for the same reason |
| `run_ver03_v3_fin-o1-8b_12259600.log` | Fin-o1-8B | 2x V100 | failed at loading (an optional `training_args.bin` reported missing); weights now loaded from safetensors only |
| `run_ver03_v3_fin-o1-8b_12259972.log` | Fin-o1-8B | 2x V100 | complete |
| `run_ver03_v3_qwen3-8b_12259599.log` | Qwen3-8B | 2x V100 | reached the 24-hour limit with the seed-2 calculator batches left; completed by the recovery job below |
| `run_ver02_v2_qwen3-14b_12259435.log` | Qwen3-14B | 1x H100 | complete (runner version 2) |
| `run_ver02_v2_fin-o1-14b_12259436.log` | Fin-o1-14B | 1x H100 | complete (runner version 2) |
| `run_ver02_v2_qwen25-32b_12259437.log`, `..._dianjin-32b_12259438.log`, `..._qwen3-32b_12259439.log` | 32B models | 2x H100 | failed at the FlashInfer import (a broken `~/.cache` link); every cache moved under the project folder |
| `run_ver03_v3_qwen25-32b_12259979.log`, `..._dianjin-32b_12259980.log`, `..._qwen3-32b_12259981.log` | 32B models | 2x H100 | failed in the custom all-reduce kernel on one node; switched off for every multi-GPU job |
| `run_ver03_v3_qwen25-32b_12265179.log` | Qwen2.5-32B-Instruct | 2x H100 | complete |
| `run_ver03_v3_dianjin-32b_12265180.log` | DianJin-R1-32B | 2x H100 | complete |
| `run_ver03_v3_qwen3-32b_12265181.log` | Qwen3-32B | 2x H100 | complete |

### Reruns and recovery

| Log | Model | What it did |
|---|---|---|
| `rerun_capped_cap_qwen25-7b_12265348.log` | Qwen2.5-7B-Instruct | reran 29 calculator answers that hit the 60-call cap, with 300 |
| `rerun_capped_cap_llama31-8b_12265349.log` | Llama-3.1-8B-Instruct | the same for 35 answers |
| `rerun_capped_cap_qwen3-14b_12265351.log` | Qwen3-14B | the same for 244 answers |
| `recover_recover_qwen3-8b_12275824.log` | Qwen3-8B (1 GPU) | ran the 308 seed-2 calculator answers the first job did not reach |
| `rerun_capped_cap_qwen3-8b_12275827.log` | Qwen3-8B (1 GPU) | reran 22 capped calculator answers, with 300 |
| `recover_recover_qwen3-32b_12281236.log` | Qwen3-32B | checked for missing batches; none |

The calculator answers of Fin-R1, DianJin-R1-7B, Fin-o1-8B and Fin-o1-14B were not rerun; 21 of them stopped at the 60-call cap ([`results/README.md`](../results/README.md#answers)).

### Grading and tables

| Log | What it did |
|---|---|
| `regrade_ver05_12265184.log` | first regrade with grader version 5 (combined table of 2026-10-15 15:01) |
| `regrade_ver05_12281215.log` | regrade of the morning of October 16 (combined table of 2026-10-16 09:08) |
| `regrade_ver05_12265185.log`, `regrade_ver05_12275832.log` | regrades after the reruns and the recovery finished |
| `regrade_ver05_12281237.log` | final regrade: combined table `combined_20261016-1919` ([`results/summary/`](../results/summary/)), from which the paper tables `paper_20261016-1951` ([`results/paper_tables/`](../results/paper_tables/)) were built |
| `summarize_ver02_12259601.log` | combined table of the version-4 grades, superseded by the version-5 regrade |
