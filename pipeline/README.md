# Pipeline

The scripts between the engine's cases and the paper's tables, in the order they run. Every script reads its inputs and writes new files; none overwrites or deletes anything. All except `run_model.py` and `compat_check.py` use the Python standard library only.

| Order | Script | Reads | Writes | Paper |
|---|---|---|---|---|
| 1 | [`build_questions.py`](build_questions.py) | `data/cases_v1_us/cases.jsonl`, `QA_set_v2.json` | `QA_set_ver03.json`, `QA_set_ver03_newco.json` | IV-C |
| 2 | [`dcf_independent.py`](dcf_independent.py) | (a library) | | IV-B |
| 3 | [`audit_questions.py`](audit_questions.py) | a question set, the cases, `data/snapshot_subset/` | `results/audit/` | IV-B |
| 4 | [`count_questions.py`](count_questions.py) | `data/questions/` | Table I (printed) | IV-C |
| 5 | [`run_model.py`](run_model.py) | the question sets, a model | `results/answers/<preset>/answers_ver02_*.jsonl` | IV-D |
| 5a | [`compat_check.py`](compat_check.py) | the V100 environment | (a pass/fail check) | IV-D |
| 5b | [`make_capped_map.py`](make_capped_map.py) | a finished run | `capped_map.json` (answers to rerun) | IV-D |
| 6 | [`grade.py`](grade.py) | a question set, answer files | `results/graded/<preset>/graded_ver05_*.csv`, `summary_ver05_*.txt` | IV-E |
| 7 | [`summarize.py`](summarize.py) | `results/graded/` | `results/summary/combined.{md,csv}` | |
| 8 | [`analyze_paper.py`](analyze_paper.py) | `results/graded/` | `results/paper_tables/` | V, Table II |
| 9 | [`list_misses.py`](list_misses.py) | graded and answer files of one configuration | `results/error_analysis/*.csv` | V-B |
| | [`pilot/`](pilot/) | | the pilot's runner and grader, kept as they were run | V-B |

Run them from this folder; their default paths are relative to it (`../data/...`, `../results/...`).

## 1. Building and checking the questions

```bash
python build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../data/questions/QA_set_v2.json \
    --dates 2019-12-31,2022-12-31 --out /tmp/QA_set_ver03.json
python build_questions.py --cases ../data/cases_v1_us/cases.jsonl --v2 ../data/questions/QA_set_v2.json \
    --dates 2025-12-31 --new-companies --out /tmp/QA_set_ver03_newco.json
python audit_questions.py --qa ../data/questions/QA_set_v2.json --out /tmp/audit
```

`build_questions.py` writes the v2 question types for other valuation dates (and, with `--new-companies`, for companies not in v2), skipping company-dates that lack a textbook or practitioner case or whose valuation falls outside the 0.3x to 3x sanity band. Every target is the engine's checkpoint and is re-checked against [`dcf_independent.py`](dcf_independent.py), an engine written from the question wording alone; the build stops if the two differ by more than 0.02%.

`audit_questions.py` runs five checks on every question-answer pair (A: keys against the independent engine; B: the answer can be rebuilt from the rounded figures printed in the question; C: inputs against the raw SEC and FRED files; D: rubric consistency; E: flags of the source cases). Its results are in [`results/audit/`](../results/audit/).

## 2. Running a model

```bash
python run_model.py --preset qwen3-32b \
    --qa ../data/questions/QA_set_v2.json,../data/questions/QA_set_ver03.json,../data/questions/QA_set_ver03_newco.json \
    --levels 2,3,4,5 --tools none,calc --seeds 0,1,2 --tp 2 --out ../results/answers/qwen3-32b
python run_model.py --preset fin-r1 --dry-run            # writes the prompts, needs no GPU
```

Needs a GPU, vLLM and transformers ([`requirements-gpu.txt`](../requirements-gpu.txt)); on the cluster it runs through [`slurm/run_model.sbatch`](../slurm/run_model.sbatch). The twelve presets, their Hugging Face ids and decoding settings are the `MODELS` table at the top of the file. Each record of an answer file holds the question id, level, tier, prompt, system prompt, `response`, `thinking` (the text before the last `</think>`), `thinking_finished`, the decoding settings and seed, `new_tokens`, `finish_reason`, the calculator calls (`calc_calls`, `n_calc`), the vLLM version and the runner.

**The calculator.** With `--tools calc` the system prompt adds a note, and the model may write `<calc>EXPRESSION</calc>`. Generation stops there, the expression is evaluated by a restricted evaluator (numbers, `+ - * / ** ( )`, `sqrt exp log abs round min max`), `<result>VALUE</result>` is appended and generation continues, up to `--max-calc-rounds` calls (300 in the paper).

**File names.** `answers_ver02_<preset>[_think][_calc]_s<seed>_<set>_L2345_<YYYYMMDD-HHMMSS>.jsonl`, with `<set>` = `v2`, `ver03` or `ver03_newco`. The `ver02` prefix names the answer-record format, which has not changed since the second version of the runner. The time stamp matters: when a question was answered twice under the same setting (the calculator reruns), the later file wins in `summarize.py`, `analyze_paper.py` and `list_misses.py`.

## 3. Grading

```bash
python grade.py --qa ../data/questions/QA_set_v2.json --self-test        # perfect answers must score 100%
python grade.py --qa ../data/questions/QA_set_v2.json --tolerance qa \
    --answers ../results/answers/qwen3-32b/answers_ver02_qwen3-32b_think_s0_v2_L2345_20261015-194418.jsonl.gz \
    --out /tmp/graded/qwen3-32b
```

Grade each answer file against the question set it was answered from (`v2` against `QA_set_v2.json`, and so on). The three modes of the paper are `--tolerance qa` (headline), `--tolerance plan` and `--tolerance plan --include-thinking`; the rules are in the header of [`grade.py`](grade.py). Answer files may be gzipped.

| Mode | Tolerances | Numbers searched for intermediate items | Used in the paper for |
|---|---|---|---|
| `qa` | each rubric item's own: rates within 0.01 percentage points, dollar values within 1% | response only | every headline number |
| `plan` | looser: values 2%, FCFF 1%, rates 0.10 pp, beta 0.02 | response only | sensitivity |
| `plan_think` | as `plan` | response and reasoning trace | Sec. V-B, "when the reasoning trace is also searched" |

Final answers are read from the response (from the reasoning trace only when the response is empty and the trace ends in an answer block), after the last answer marker the model used (a `FINAL ANSWER:` line, a "Final Answer" or "Final Response" heading, an `<answer>` block or `\boxed{}`).

Each row of `graded_ver05_<mode>_<answers>.csv` is one rubric item of one answer:

| Column | Meaning |
|---|---|
| `question_id`, `tier`, `level`, `item`, `kind`, `step`, `component`, `checkpoint`, `criterion` | the rubric item (see [`data/README.md`](../data/README.md)) |
| `points`, `earned` | points possible and earned |
| `correct` | `True` or `False`; empty when the item is excluded |
| `excluded` | why an item is not scored: rounding not auto-graded, input given in the data table, zero target, target already in the prompt |
| `marker` | which final-answer marker was found: `exact`, `other case`, `Final Response heading`, `answer tag`, `boxed`, ... or `missing` |
| `note` | for trap and alternative items: matched, but the final answer was also correct (not counted) |

`summary_ver05_<mode>_<answers>.txt` gives the same answer file in words: final answers correct by tier and level, markers found, answers cut by the token limit, trap falls and points by step.

## 4. Tables

```bash
python analyze_paper.py --graded ../results/graded --out /tmp/paper_tables       # identical to results/paper_tables/
python summarize.py --graded ../results/graded --out /tmp/summary
python count_questions.py
```

`analyze_paper.py` pools the graded files of every (mode, model, tool, seed) across the three question sets, then reports accuracy by tier and date, rubric scores, step scores on the full textbook valuations, the chain gap and the trap falls; seeds are shown as mean +/- sd and as pooled counts. The parsing of the setting from the file name is in `parse()`: the model is the first token after `answers_` (and `ver02_`), `calc` marks the calculator, `s<digit>` the seed, and `ver03` / `newco` the question set.

`list_misses.py` lists the questions a configuration got wrong with the key and the model's final line, as the starting point of a manual error analysis:

```bash
python list_misses.py --graded ../results/graded/pilot --answers ../results/answers/pilot \
    --config Qwen3-32B_think --mode qa --out /tmp/pilot_qwen3-32b_misses.csv
```

## 5. Evaluating another model

Any model can be scored with the same grader, including an API model. Build the prompts exactly as the paper did, write one JSON line per answer, then grade and analyze:

```python
import json, sys
sys.path.insert(0, "pipeline")                      # from the repository root
from run_model import SYSTEM, load, build_prompts    # no GPU libraries are imported

questions = load("data/questions/QA_set_v2.json")
with open("answers_mymodel_s0_v2_L2345_20261101-120000.jsonl", "w") as out:
    for p in build_prompts(questions, {2, 3, 4, 5}):
        reply = my_model(system=SYSTEM, user=p["prompt"])   # your model call
        out.write(json.dumps({"question_id": p["question_id"], "level": p["level"],
                              "prompt": p["prompt"], "response": reply}) + "\n")
```

```bash
python pipeline/grade.py --qa data/questions/QA_set_v2.json --tolerance qa \
    --answers answers_mymodel_s0_v2_L2345_20261101-120000.jsonl --out my_graded/mymodel
python pipeline/analyze_paper.py --graded my_graded --out my_tables
```

- **All 308 questions:** repeat for `QA_set_ver03.json` and `QA_set_ver03_newco.json`, and grade each answer file against the set it answered.
- **File names** carry the setting that `analyze_paper.py` reads: `answers_<model>[_calc]_s<seed>_<set>_L2345_<YYYYMMDD-HHMMSS>.jsonl`, with `<set>` = `v2`, `ver03` or `ver03_newco`.
- **Keep the `prompt` field**: rubric items whose target is already printed in the prompt are excluded from scoring.
- **Reasoning models:** put the reasoning trace in a `thinking` field; only `response` is read for final answers.
- **Calculator setting:** append `CALC_NOTE` from `run_model.py` to the system prompt, answer each `<calc>...</calc>` with `<result>...</result>` (the loop and the evaluator are in `run_model.py`), and add `_calc` to the file name.

## 6. History

The scripts here are the versions that produced the paper. Their earlier versions, what changed and why (for example, the grader's recognition of the fine-tunes' answer formats and the calculator cap raised from 60 to 300) are in [`docs/PIPELINE.md`](../docs/PIPELINE.md); the jobs that ran them are indexed in [`logs/README.md`](../logs/README.md).
