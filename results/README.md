# Results

Everything the models produced and everything computed from it (paper, Section V). Each folder can be rebuilt from the one before it with the commands in [`docs/REPRODUCE.md`](../docs/REPRODUCE.md), and the rebuilt files are byte-identical to the ones here.

| Folder | Contents | Built by | Paper |
|---|---|---|---|
| [`answers/`](answers/) | Every model answer: 18,480 answers of the twelve models (plus 330 calculator reruns) and 552 pilot answers | [`pipeline/run_model.py`](../pipeline/run_model.py), [`pipeline/pilot/run_model.py`](../pipeline/pilot/run_model.py) | IV-D |
| [`graded/`](graded/) | One graded file and one summary per answer file and grading mode (1,260 files) | [`pipeline/grade.py`](../pipeline/grade.py) | IV-E |
| [`paper_tables/`](paper_tables/) | The paper's tables in the three grading modes, per setting and per seed | [`pipeline/analyze_paper.py`](../pipeline/analyze_paper.py) | V, Table II |
| [`summary/`](summary/) | One row per answer configuration: accuracy by tier and level, rubric score, trap and basic-share hits | [`pipeline/summarize.py`](../pipeline/summarize.py) | |
| [`audit/`](audit/) | The answer-key audit of the three question sets (checks A to E) | [`pipeline/audit_questions.py`](../pipeline/audit_questions.py) | IV-B |
| [`error_analysis/`](error_analysis/) | The 16 incorrect final answers of the pilot run of Qwen3-32B | [`pipeline/list_misses.py`](../pipeline/list_misses.py) | V-B |

## `answers/`

One folder per model preset (the `MODELS` table in [`pipeline/run_model.py`](../pipeline/run_model.py) maps each preset to its Hugging Face model) and `pilot/`. Files are gzipped JSON Lines, one answer per line; the fields are listed in [`pipeline/README.md`](../pipeline/README.md#2-running-a-model). File names:

```text
answers_ver02_qwen3-32b_think_calc_s1_ver03_newco_L2345_20261015-194418.jsonl.gz
              |         |     |    |  |           |     +-- run time stamp (later wins for a question answered twice)
              |         |     |    |  |           +-------- Levels 2-5
              |         |     |    |  +-------------------- question set: v2 (2025), ver03 (2019, 2022), ver03_newco (held-out)
              |         |     |    +----------------------- seed (0 for the greedy models)
              |         |     +---------------------------- calculator on (absent: off)
              |         +---------------------------------- reasoning (thinking) model
              +-------------------------------------------- model preset
```

Per model there are 6 files for the three greedy models (2 tools x 3 sets) and 18 for the nine reasoning models (2 tools x 3 seeds x 3 sets), plus the reruns:

| Preset | Extra files | Why |
|---|---|---|
| `qwen25-7b`, `llama31-8b`, `qwen3-14b`, `qwen3-8b` | calculator answers with a later time stamp, `capped_map.json` | answers that hit the 60-call calculator cap of the first pass, rerun with 300 |
| `qwen3-8b` | batches with a later time stamp, `missing_map_*.json` | the batches its first job did not reach before the 24-hour limit |
| `qwen3-32b` | `missing_map_*.json` (empty) | a recovery check that found nothing missing |
| `fin-r1` | `capped_map.json` | the 11 Fin-R1 answers that hit the 60-call cap; they were not rerun (see below) |

**Calculator cap.** The first pass allowed 60 calculator calls per answer; the runs that started after the default was raised to 300 (the 32B models and every rerun) record `max_calc_rounds = 300`, the earlier ones record no cap and ran with 60. For most answers the difference never mattered, because they used fewer than 60 calls. The answers that did reach 60 were rerun with 300 for Qwen2.5-7B, Llama-3.1-8B, Qwen3-8B and Qwen3-14B. Twenty-one calculator answers of four fine-tunes were not rerun and stopped at 60 calls: Fin-R1 11, DianJin-R1-7B 4, Fin-o1-14B 4 and Fin-o1-8B 2, out of 924 calculator answers each. They are graded as written: 12 of them have no final answer, 2 are correct and 7 are incorrect, so a rerun could raise each of these models' calculator accuracy on all 308 questions (mean over seeds) by at most 0.2 (Fin-o1-8B) to 1.2 points (Fin-R1).

`pilot/` holds the pilot runs of Qwen2.5-7B-Instruct, Qwen2.5-32B-Instruct and Qwen3-32B (see [`pipeline/pilot/README.md`](../pipeline/pilot/README.md)); their file names follow the pilot runner (`answers_<model>[_think][_v2]_L<levels>[_S<shard>]_<time>.jsonl.gz`).

## `graded/`

For each answer file and each of the three grading modes, `graded_ver05_<mode>_<answer file>.csv` (one row per rubric item; columns in [`pipeline/README.md`](../pipeline/README.md#3-grading)) and `summary_ver05_<mode>_<answer file>.txt`. `<mode>` is `qa` (the paper's headline), `plan` or `plan_think`. "ver05" is the version of the grader that produced the paper.

## `paper_tables/`

`tables_<mode>.md` has three sections; `per_seed_<mode>.csv` has one row per (model, tool, seed).

| Section of `tables_qa.md` | Contents | Paper |
|---|---|---|
| A. Accuracy by model and tool | final-answer accuracy on the 2025 set (184) and on all 308 questions, the rubric score, and pooled counts per tier and date. Rows with a capitalized name and one seed (`Qwen2.5-32B-Instruct`, `Qwen2.5-7B-Instruct`, `Qwen3-32B`) are the pilot runs on the 2025 set; the lower-case presets are the main runs | Table II; V-A; V-C |
| B. Step scores | rubric points earned in Steps 2 to 5 of the full textbook valuations, and their final answers | V-B |
| C. Chain gap and trap falls | firms whose Half A and Half B are both correct, and how many of those still failed the full textbook valuation, per date set; trap falls | V-A |

Table II reads columns *single*, *full tb* and *all acc (308)* of section A in the rows `none` (without calculator) and `calc` (*All, +C*). The step scores "when the reasoning trace is also searched" are section B of `tables_plan_think.md`, which also uses the looser `plan` tolerances.

## `audit/`

For each question set, `QA_AUDIT_ver01_<set>.md` summarizes five checks, and `<set>_<check>.csv` lists every row checked:

| Check | What is compared | Result |
|---|---|---|
| A. Answer keys | every final, step, middle and alternative target and every input against the independent engine | all 3,997 targets match; computed targets exactly, printed inputs within 0.07% (rounding to $0.1 million) |
| B. Reproducible from the question | each answer recomputed from the rounded figures printed in its question | all 308 within tolerance; the largest gap uses 4% of the tolerance (0.033% of the value per share for textbook questions, 0.041% for practitioner questions) |
| C. Raw filings | every historical input against the SEC XBRL fact it came from, rates against FRED, market value against the stored close | all match (four prices after undoing a later split or spin-off) |
| D. Rubric consistency | points, printed numbers, separation of trap and alternative values from the correct answer | informational flags only |
| E. Case flags | source cases outside the 0.3x-3x sanity band | none used |

Rerunning the audit from this repository reproduces checks A, B, D and E exactly; check C reproduces apart from its market-value rows, which need the Yahoo Finance price files that are not redistributed ([`data/README.md`](../data/README.md#3-raw-data-snapshot_subset-snapshot_manifest)).
