# Paper

[`main.tex`](main.tex) is the paper in IEEE conference format (`IEEEtran`), with its figures drawn in TikZ and its references inline, so it compiles on its own:

```bash
cd paper
pdflatex main.tex && pdflatex main.tex      # or: tectonic main.tex
```

## Where each part of the paper comes from

The paper reports grading mode `qa` unless stated otherwise; the three modes (`qa`, `plan`, `plan_think`) are described in [`pipeline/README.md`](../pipeline/README.md#3-grading).

| In the paper | Where to find it |
|---|---|
| Fig. 1, error propagation for PPL Corporation | Pilot answer of Qwen3-32B to question `PPL-05`, field `thinking` (1.0588^5 taken as 1.3556 instead of 1.3309): [`results/answers/pilot/answers_Qwen3-32B_think_L3_20261013-234908.jsonl.gz`](../results/answers/pilot/); answer key in [`data/questions/QA_set_v2.json`](../data/questions/QA_set_v2.json) (`PPL-05`, $17.86) |
| Fig. 2, benchmark design traced for PPL | Case `US-PPL-2025-12-31-textbook` in [`data/cases_v1_us/cases.jsonl`](../data/cases_v1_us/), questions `PPL-01` to `PPL-11` and their rubric items in [`data/questions/QA_set_v2.json`](../data/questions/QA_set_v2.json) |
| Table I, questions by valuation set and tier | `python pipeline/count_questions.py` (counts from [`data/questions/`](../data/questions/)) |
| Sec. IV-A, point-in-time company data | [`engine/src/dcfbench/data/`](../engine/src/dcfbench/data/) (EDGAR, FRED, Yahoo, Damodaran adapters), [`data/snapshot_manifest/`](../data/snapshot_manifest/), [`data/cases_v1_us/`](../data/cases_v1_us/) |
| Sec. IV-B, policies and answer engine | [`policies.py`](../engine/src/dcfbench/policies.py), [`engine.py`](../engine/src/dcfbench/engine.py), [`forecast.py`](../engine/src/dcfbench/forecast.py); textbook example reproduced to the cent: [`test_engine_rwj.py`](../engine/tests/test_engine_rwj.py); independent re-implementation: [`pipeline/dcf_independent.py`](../pipeline/dcf_independent.py), checks A and B in [`results/audit/`](../results/audit/) |
| Sec. IV-C, staged question tiers | [`pipeline/build_questions.py`](../pipeline/build_questions.py), [`data/questions/`](../data/questions/) |
| Sec. IV-D, models and inference settings | `MODELS` and `SYSTEM` in [`pipeline/run_model.py`](../pipeline/run_model.py), [`slurm/`](../slurm/), [`logs/`](../logs/) |
| Sec. IV-E, rubric-based grading and metrics | [`pipeline/grade.py`](../pipeline/grade.py), [`pipeline/analyze_paper.py`](../pipeline/analyze_paper.py) |
| Table II, accuracy without and with the calculator | [`results/paper_tables/tables_qa.md`](../results/paper_tables/tables_qa.md), section A: columns *single*, *full tb*, *all acc (308)*, rows *none* and *calc* |
| Sec. V-A (RQ1), workflow length, chain gap, other dates | `tables_qa.md`, section A (columns *@2019*, *@2022*, *@2025n*) and section C (chain gap, column *v2 2025*) |
| Sec. V-B (RQ2), step scores from the response alone | `tables_qa.md`, section B |
| Sec. V-B (RQ2), step scores with the reasoning trace searched | [`results/paper_tables/tables_plan_think.md`](../results/paper_tables/tables_plan_think.md), section B |
| Sec. V-B (RQ2), the 16 incorrect answers of the pilot run of Qwen3-32B | [`results/error_analysis/pilot_qwen3-32b_misses.csv`](../results/error_analysis/pilot_qwen3-32b_misses.csv) (the classification into omitted conventions and errors after the debt bridge was done by hand) |
| Sec. V-C (RQ3), scale, reasoning, fine-tuning, calculator | `tables_qa.md`, section A (column *all acc (308)*, rows *none* and *calc*) |
| Sec. VI, limitations | [`docs/PIPELINE.md`](../docs/PIPELINE.md#4-known-limitations-and-deviations) |
