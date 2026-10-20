# Pipeline: design, history and known limitations

This note explains why the pipeline is built the way it is, how its scripts evolved before they produced the paper, and what a reader should know about the data and the runs. For how to run each step see [`pipeline/README.md`](../pipeline/README.md) and [`REPRODUCE.md`](REPRODUCE.md).

## 1. Stages

Every number in the paper passes through five stages, and a choice at one stage affects everything after it.

| Stage | What happens | Code | Output |
|---|---|---|---|
| A. Cases | SEC filings, FRED rates, prices and Damodaran's tables become inputs; the engine applies a policy and stores every checkpoint | [`engine/`](../engine/) | [`data/cases_v1_us/`](../data/cases_v1_us/) |
| B. Questions | A case becomes question text (which figures are printed, how the policy is worded), rubric items, traps and tolerances | [`pipeline/build_questions.py`](../pipeline/build_questions.py) | [`data/questions/`](../data/questions/) |
| C. Model runs | System prompt, calculator on or off, token budget, calculator cap, seeds | [`pipeline/run_model.py`](../pipeline/run_model.py), [`slurm/`](../slurm/) | [`results/answers/`](../results/answers/) |
| D. Grading | Find the final-answer marker, extract numbers, match them at a tolerance, award points | [`pipeline/grade.py`](../pipeline/grade.py) | [`results/graded/`](../results/graded/) |
| E. Reporting | Pool seeds and question sets, compute accuracy, step scores, chain gap and trap falls | [`pipeline/analyze_paper.py`](../pipeline/analyze_paper.py) | [`results/paper_tables/`](../results/paper_tables/) |

Stages A and B are checked independently of each other: [`pipeline/dcf_independent.py`](../pipeline/dcf_independent.py) recomputes every target from the question wording without the engine's code, and [`pipeline/audit_questions.py`](../pipeline/audit_questions.py) compares keys, question texts and raw filings ([`results/audit/`](../results/audit/)).

## 2. Design choices

**The key is the engine's value, not the market price.** A model that has seen a company's filings or prices in training cannot recall the answer, because the value follows from the stated policy (for PPL, $17.86 against a price of $35.02).

**Every judgment call is stated.** The question prints the risk-free instrument, the equity risk premium, the beta and its adjustment, the tax rule, the discounting convention, the terminal growth rate and the cash treatment (Assumptions 1-15), so exactly one answer exists. The practitioner policy changes seven of these rules on the same firms, which separates the method from the arithmetic.

**Step 1 is supplied.** Every question prints the historical figures it needs, so the benchmark tests the valuation itself, not retrieval from a filing (Level 1 retrieval questions exist in v2 but are not evaluated).

**The halves compose exactly.** Half A ends at the five free cash flows; Half B starts from the engine's free cash flows. Together they cover the full textbook valuation, so a firm whose halves are both correct but whose full valuation is wrong has failed only in combining them: the chain gap.

**Deterministic grading.** No LLM judge: each rubric item has a numeric target and a tolerance. Items the grader cannot judge fairly are excluded rather than failed: rounding instructions, inputs already given in a data table, zero targets, and targets printed in the prompt (a model that copies a printed number has not computed it).

**Final answers are read after the last answer marker.** The requested `FINAL ANSWER:` line is preferred; headings, `<answer>` blocks and `\boxed{}` are read for models trained to answer that way. A reply with no marker scores zero on its final item, rather than letting a stray intermediate number count as the answer.

**Trap and alternative items carry 0 points** and count as a hit only when the final answer is wrong, because a trap figure within tolerance of the correct answer would otherwise be counted for correct answers too.

**The calculator is plain text** (`<calc>...</calc>`, `<result>...</result>`), so every model gets the same tool regardless of its native tool format, and the evaluator accepts arithmetic only.

**Paired hardware.** Each financial fine-tune runs on the same GPU type and vLLM version as its base model.

## 3. History of the scripts

The repository holds the versions that produced the paper, under plain names. Result files and logs carry the internal version tags.

### Question sets

| Set | Date | Content |
|---|---|---|
| `QA_set_v1` | October 13, 2026 | 40 questions on 8 companies (Levels 1-3, textbook), the pilot |
| `QA_set_v2` | October 14 | v1 unchanged plus 20 companies and the tiers basic, half, trap and complex: 200 questions, 184 evaluated |
| `QA_set_ver03`, `QA_set_ver03_newco` | October 14 | the v2 question types at 2019 and 2022 for the v2 companies with complete cases (13), and at 2025 for five companies not in v2 |

### Runner (`pipeline/run_model.py`)

| Version | Change |
|---|---|
| pilot ([`pipeline/pilot/run_model.py`](../pipeline/pilot/run_model.py)) | transformers `generate`, one question at a time; thinking mode; Level 3 data table |
| 2 | vLLM with batched generation and the model's own chat template; the calculator tool; seeds per question; model presets with each model's recommended decoding; several question sets per job. Ran Qwen3-14B and Fin-o1-14B, with a 60-call calculator cap |
| 3 (this repository) | compatibility with vLLM 0.10.1 and transformers 5 on the V100 nodes (tokenizer property, RoPE fields, custom all-reduce and prefix caching off, safetensors only); calculator cap raised to 300; `--only-map` to rerun selected questions; the runner and cap recorded in each answer |

On one H100 with vLLM 0.31, version 2 and version 3 differ only in the calculator cap, so the 14B runs are comparable with the others; the Qwen3-14B answers that hit the 60-call cap were rerun at 300.

### Grader (`pipeline/grade.py`)

| Version | Change |
|---|---|
| pilot 1-3 ([`pipeline/pilot/grade.py`](../pipeline/pilot/grade.py)) | number matching at the rubric's tolerance; final items read after `FINAL ANSWER:` (version 2); trap and alternative items reported separately (version 3) |
| 4 | the marker matched in any letter case, and the last one used; no fall-back to the whole reply when no marker is found; trap and alternative hits only when the final answer is wrong (in version 3, 39 of 41 alternative hits were on correct answers); the `plan` tolerance mode; `--include-thinking`; replies cut by the token limit reported |
| 5 (this repository) | the answer formats of the financial fine-tunes (`\boxed{}`, `<answer>` blocks, "Final Answer" and "Final Response" headings, an answer left inside an unfinished thinking block). Under version 4 these models scored zero on every final item although they had answered |

Version 5 regraded every answer, the pilot's included, for the paper.

### Analysis

[`pipeline/summarize.py`](../pipeline/summarize.py) pools graded files by configuration (one row per model, tool and seed); [`pipeline/analyze_paper.py`](../pipeline/analyze_paper.py) adds the paper's tier groups, the step scores, the chain gap and the trap falls, and summarises seeds. Both take the later file when a question was answered twice under one setting.

## 4. Known limitations and deviations

Stated in the paper (Section VI):

- U.S. large-capitalization firms at three dates, and open-weight models up to 32B parameters.
- The reasoning models had a larger token budget (24,576) than the greedy models (8,192).
- The trap questions state the correct rule next to the tempting figure, so they test following a stated rule under distraction rather than knowing the convention.

About the data:

- **EBIT recipe.** When a 10-K has no `OperatingIncomeLoss` tag, the engine builds EBIT as income before taxes plus interest expense; this also contains non-operating items. It applies to 30 evaluated questions of CVX, ETN, GE, JNJ, MRK, SHW, XOM and SLB. Each such question says so in its text ("case definition: pretax income plus interest expense"), and the models are given the figure, so they are not asked to find EBIT themselves. Every tag fallback is logged in [`data/cases_v1_us/fallbacks.csv`](../data/cases_v1_us/fallbacks.csv).
- **Prices.** Yahoo Finance closes are adjusted backwards for later splits and spin-offs; the engine undoes that, so the price is the one that traded on the valuation date. The audit's check C confirms the arithmetic for every such company-date.
- **Classification and survivorship.** GICS sectors are those of October 2026, applied to 2019 and 2022, and the sector pool was ranked by October 2026 market capitalization, so a company that was large in 2019 but is small today is not in the sample.
- **Industry betas and synthetic ratings** stand in for firm-specific estimates, as the policies state.

About the runs:

- **Calculator cap.** 21 calculator answers of Fin-R1 (11), DianJin-R1-7B (4), Fin-o1-14B (4) and Fin-o1-8B (2) ran under the first pass's 60-call cap and were not rerun with 300; all other answers either ran with 300 or used fewer than 60 calls. The largest possible effect is 1.2 points of Fin-R1's calculator accuracy ([`results/README.md`](../results/README.md#answers)).
- **Pilot budgets.** The pilot runs of the Qwen2.5 models used up to 4,096 new tokens, the main runs 8,192. The pilot is used only for the error analysis of Section V-B and the example of Fig. 1; Table II comes from the main runs.
- **Sampling.** The reasoning models are sampled, so a rerun reproduces the results in distribution, not answer by answer.
