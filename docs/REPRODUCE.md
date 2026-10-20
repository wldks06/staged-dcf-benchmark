# Reproducing the paper

Five levels, from rebuilding the tables out of the published grades (a minute, any laptop) to rerunning the models (GPU cluster). Each level checks its output against the files in this repository. Commands run from the repository root; outputs go to `/tmp/staged-dcf` (change with `OUT=...`).

| Level | What is rebuilt | Needs | Time | Command |
|---|---|---|---|---|
| 1 | Paper tables from the graded files | Python 3 | 1 minute | `make tables` |
| 2 | Every graded file from the model answers, then the tables | Python 3 | about 4 minutes | `make regrade` |
| 3 | Question sets from the cases, answer-key audit, pilot error list | Python 3 | 2 minutes | `make questions audit misses` |
| 4 | Engine tests; optionally the cases from the original sources | Python 3.11, pip, network for a new snapshot | 1 minute (tests) | `make engine-test` |
| 5 | Model answers | GPUs, vLLM, the models | the paper's jobs ran for about 41 hours, in parallel | [`slurm/submit_all.sh`](../slurm/submit_all.sh) |

## Level 1: paper tables

```bash
make tables
```

Expected: `identical` for `tables_qa.md`, `tables_plan.md`, `tables_plan_think.md`, the three `per_seed_*.csv` and `summary/combined.{md,csv}`. Table II of the paper is section A of `tables_qa.md` ([`results/README.md`](../results/README.md#paper_tables)). Table I:

```bash
make table1
```

## Level 2: grading

```bash
make regrade
```

Runs the grader's self-test (perfect answers must score 100%), grades all 210 answer files in the three modes, compares each of the 1,260 outputs with [`results/graded/`](../results/graded/), and rebuilds the tables from the new grades. Expected: `regraded 1260 files, 0 differ from results/graded` and `identical` for the six table files.

## Level 3: questions, audit, error list

```bash
make questions    # QA_set_ver03 and QA_set_ver03_newco rebuilt from the cases: questions, rubric and cases identical
make audit        # checks A, B, D and E identical; check C needs the price files for its market-value rows
make misses       # the 16 incorrect final answers of the pilot run of Qwen3-32B: identical
```

`QA_set_v2.json` itself was written by the authors' first question builder, which is not part of this repository; pointed at 2025-12-31, `build_questions.py` reproduces all 40 of its half-DCF questions word for word and the final answers of all 68 v2 questions it rebuilds, and the audit checks every one of v2's 2,106 targets against the independent engine.

## Level 4: the engine

```bash
make engine-test  # 350 passed, 6 skipped
```

To rebuild the cases from SEC EDGAR, FRED, Yahoo Finance and Damodaran, follow [`engine/README.md`](../engine/README.md#rebuild-the-cases-from-the-original-sources). A new snapshot will not match the paper's byte for byte, because the sources revise their data; compare it with [`data/snapshot_manifest/`](../data/snapshot_manifest/).

## Level 5: model runs

1. Create the two conda environments of [`slurm/README.md`](../slurm/README.md#setup) and install [`requirements-gpu.txt`](../requirements-gpu.txt).
2. `export REPO_ROOT=$PWD MODEL_STORE=/path/to/model_store`, set the allocation in the `#SBATCH -A` lines.
3. `sbatch slurm/download_models.sbatch`, then `sbatch slurm/compat_check.sbatch` (V100 only).
4. `bash slurm/submit_all.sh`: two smoke tests, the twelve model jobs, the regrade.

The reasoning models are sampled, so a rerun reproduces the paper's numbers in distribution rather than answer by answer; vLLM's batching on a different GPU or library version can also change greedy outputs slightly. The published answers in [`results/answers/`](../results/answers/) are the ones the paper reports.
