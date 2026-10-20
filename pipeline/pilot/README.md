# Pilot runner and grader

The first runner and grader of the benchmark, kept as they were run on October 13 and 14, 2026, so that the pilot answers in [`results/answers/pilot/`](../../results/answers/pilot/) can be traced to the code that produced them. Only the cluster paths and the allocation name in `run_job.sh` were replaced by variables.

| File | What it did |
|---|---|
| [`run_model.py`](run_model.py) | Ran one model through Hugging Face transformers (`model.generate`, one question at a time), with the same system prompt as the main runs and, for Level 3, the 10-K figures attached as a data table. Options for thinking mode, levels, shards and excluding the questions of an earlier set |
| [`run_job.sh`](run_job.sh) | The Slurm job for one model on one H100 |
| [`grade.py`](grade.py) | The pilot grader (its version 3). Superseded by [`../grade.py`](../grade.py), which re-graded every pilot answer for the paper ([`results/graded/pilot/`](../../results/graded/pilot/)) |

Runs (logs in [`logs/pilot/`](../../logs/pilot/)): Qwen2.5-7B-Instruct, Qwen2.5-32B-Instruct and Qwen3-32B in thinking mode, first on the 24 Level 2-3 questions of `QA_set_v1.json` (October 13), then on the remaining 160 Level 2-5 questions of `QA_set_v2.json` (October 14, `--exclude-qa QA_set_v1.json`), one pass each and no calculator: the Qwen2.5 models greedy with up to 4,096 new tokens, Qwen3-32B sampled (temperature 0.6, top-p 0.95, top-k 20) with up to 24,576. Together they cover the 184 evaluated questions of v2.

The pilot run of Qwen3-32B is the one the paper analyses by hand in Section V-B (16 incorrect final answers, [`results/error_analysis/pilot_qwen3-32b_misses.csv`](../../results/error_analysis/pilot_qwen3-32b_misses.csv)) and the source of the example in Fig. 1.
