# Data

Everything a model sees, every answer key, and the evidence the keys were built from (paper, Sections IV-A to IV-C).

| Folder | What it holds | Built by |
|---|---|---|
| [`questions/`](questions/) | The 308 evaluated questions with their rubrics, plus the pilot set | `QA_set_v1/v2`: the authors' question builder; `QA_set_ver03*`: [`pipeline/build_questions.py`](../pipeline/build_questions.py) |
| [`cases_v1_us/`](cases_v1_us/) | The engine's cases: inputs with provenance, policy and every checkpoint | [`engine/`](../engine/) (`dcfbench generate-us --universe sector --version v1`) |
| [`snapshot_subset/`](snapshot_subset/) | Raw SEC EDGAR company facts (68 companies) and FRED rate series, used by the answer-key audit | copied from the frozen snapshot `snap-2026-10-05-a` |
| [`snapshot_manifest/`](snapshot_manifest/) | Source URL, fetch time, size and SHA-256 of every raw payload of that snapshot | [`engine/src/dcfbench/data/snapshot.py`](../engine/src/dcfbench/data/snapshot.py) |

## 1. Question sets

| File | Valuation date(s) | Firms | Evaluated questions (Levels 2-5) | Role in the paper |
|---|---|---|---|---|
| [`QA_set_v2.json`](questions/QA_set_v2.json) | 2025-12-31 | 28 | 184 (+16 Level 1 questions, not evaluated) | main set |
| [`QA_set_ver03.json`](questions/QA_set_ver03.json) | 2019-12-31, 2022-12-31 | 13 | 104 | same firms, other rate environments |
| [`QA_set_ver03_newco.json`](questions/QA_set_ver03_newco.json) | 2025-12-31 | 5 | 20 | held-out firms |
| [`QA_set_v1.json`](questions/QA_set_v1.json) | 2025-12-31 | 8 | 24 (+16 Level 1) | pilot only; its 40 questions are contained in v2, unchanged apart from an added `tier` field |

Level 1 questions ("find the number in the 10-K") need the filing itself, which a model without tools does not have, so they are not evaluated. `python pipeline/count_questions.py` prints the paper's Table I from these files.

### 1.1 File layout

Each file is one JSON object:

```text
{
  "meta":       { name, source_cases, valuation_date(s), points_scheme, tolerances, tiers, ... },
  "questions":  [ one object per question ],
  "rubric":     [ one object per rubric item, linked by question_id ],
  "cases_used": [ one object per case: ticker, sector, case_id, snapshot_id, synthetic rating,
                  engine value per share, market price ]
}
```

**Question fields**

| Field | Example | Meaning |
|---|---|---|
| `question_id` | `PPL-05`, `CMCSA-2019-07` | `<TICKER>-<NN>` in v1/v2, `<TICKER>-<YEAR>-<NN>` in ver03 (numbering below) |
| `level`, `level_name` | `3`, `Full DCF` | 1 find the number, 2 one calculation, 3 full DCF, 4 Half DCF A, 5 Half DCF B |
| `tier` | `basic`, `trap`, `half`, `complex`, `half@2019` | question family (mapping to the paper's tiers below); `@<YEAR>` marks the ver03 sets |
| `ticker`, `company`, `sector`, `valuation_date` | `PPL`, `PPL Corporation`, `Utilities`, `2025-12-31` | the company-date |
| `case_id`, `policy` | `US-PPL-2025-12-31-textbook`, `textbook` | the engine case the key comes from (in `cases_v1_us/cases.jsonl`) |
| `step`, `component` | `Steps 1-5`, `Full DCF` | where in the DCF the question sits |
| `question` | full text | the prompt, with the policy and every figure the question needs |
| `final_answer`, `unit`, `total_points` | `WACC 5.88%; ...; $17.86 per share` | the key as text |

**Rubric item fields**

| Field | Example | Meaning |
|---|---|---|
| `question_id`, `item` | `PPL-03`, `2` | the question and the item's position |
| `kind` | `final`, `step`, `middle`, `input`, `rounding`, `trap`, `alternative` | final answer (10 points), step result (5), intermediate value (2), input (1), rounding instruction (1), and two 0-point diagnostic items: the figure a trap produces and the value per share on basic instead of diluted shares |
| `points` | `10` | points of the item |
| `criterion` | `Value per share = $17.86` | the item in words |
| `target` | `17.8566` | the number to match; several numbers are separated by `;` |
| `tol_type`, `tol_value`, `tolerance` | `rel`, `0.01`, `+/-1% of the target` | `rel` relative, `abs_pp` percentage points, `abs` absolute, `exact` at the stated rounding |
| `step`, `component`, `checkpoint` | `Step 5. Value and decide`, `price_per_share` | the engine checkpoint the target is read from |

### 1.2 Question numbering and tiers

The paper's tier of a question is given by the pair (`tier`, `level`):

| `tier` | `level` | Paper tier | Policy |
|---|---|---|---|
| `basic` | 2 | Single | textbook |
| `trap` | 2 | Trap | textbook |
| `half`, `half@<YEAR>` | 4 | Half A (Steps 2-3) | textbook |
| `half`, `half@<YEAR>` | 5 | Half B (Steps 4-5) | textbook |
| `basic`, `basic@<YEAR>` | 3 | Full TB | textbook |
| `complex`, `complex@<YEAR>` | 3 | Full PR | practitioner |
| `basic` | 1 | not evaluated | textbook |

The number at the end of a `question_id` follows the order in which the sets were written, so it is not the same for every company. Classify questions by (`tier`, `level`), never by the suffix.

| Companies | `-01` | `-02` | `-03` | `-04` | `-05` | `-06` | `-07` | `-08` | `-10`, `-11` |
|---|---|---|---|---|---|---|---|---|---|
| 8 pilot firms of v1 (BKNG, CMCSA, CRH, JNJ, PM, PPL, UNP, WMB) | L1 | L1 | Single | Single | Full TB | Half A | Half B | Full PR | Trap |
| 12 further v2 firms | Single | Single | Full TB | | | Half A | Half B | Full PR | Trap |
| 8 further v2 firms (single and full textbook only) | Single | Single | Full TB | | | | | | |
| ver03 sets (`<TICKER>-<YEAR>-NN`) | | | | | Full TB | Half A | Half B | Full PR | |

### 1.3 How a question is built

Every number in a question and its rubric is read from the stored checkpoints of its case, and every target is checked against an independent engine ([`pipeline/dcf_independent.py`](../pipeline/dcf_independent.py)). Differences between v2 and ver03, both deliberate, are listed in the header of [`pipeline/build_questions.py`](../pipeline/build_questions.py): ver03 prints every Level 3 figure in the question text (for v2 the runner appends the figures the text leaves out, so the information a model sees is the same), and every ver03 Level 3 and Level 5 question carries the basic-share alternative item. Rebuilding ver03 from the cases reproduces the published files exactly (`make questions`).

The only edit made to these files for publication: `meta.source_cases`, which recorded the absolute path of the case file on the machine that built the set, now reads `data/cases_v1_us/cases.jsonl`.

## 2. Cases (`cases_v1_us/`)

The engine's output for the U.S. sector-balanced universe: 484 cases for 68 companies and 125 company-dates (2019: 43, 2022: 38, 2025: 44), each under the textbook, practitioner and two trap policies (T1, T2). The questions use the textbook and practitioner cases of 33 of these companies.

| File | Contents |
|---|---|
| `cases.jsonl` | one case per line: `company`, `valuation_date`, `policy` (every judgment call as a field), `policy_label`, `snapshot_id`, `inputs` (three fiscal years of statement items, market data, rates, beta, rating, and the `provenance` of each input: XBRL tag, accession number, filing date, period end, or series and observation date), `checkpoints` (tax rate, risk-free rate, ERP, levered beta, cost of equity and debt, weights, WACC, five FCFFs, terminal value, present values, EV, excess cash, equity, value per share, the forecast detail and a sensitivity grid) and `trap_answers` |
| `summary.json` | counts by date, exclusion reasons, fallbacks, trap visibility |
| `exclusions.csv` | every company-date that was dropped, with its reasons (financial SIC code, fiscal year end not December, negative EBIT or FCFF, a missing input, outside the five largest of its sector, ...) |
| `fallbacks.csv` | every input that was not found under its first-choice XBRL tag, with the tag used instead |
| `notes.csv` | the sector rank of every company-date and the adjustments to share counts (rebased for splits, rescaled units); a price un-adjusted for a later split or spin-off is marked in the `provenance` of its `price` input ("close as traded, later splits undone") |
| `inspect.csv` | cases whose DCF enterprise value is outside 0.3x to 3x the market enterprise value; no question uses these |

The engine's rules are in [`engine/src/dcfbench/engine.py`](../engine/src/dcfbench/engine.py), [`forecast.py`](../engine/src/dcfbench/forecast.py) and [`policies.py`](../engine/src/dcfbench/policies.py).

## 3. Raw data (`snapshot_subset/`, `snapshot_manifest/`)

All cases come from one frozen snapshot, `snap-2026-10-05-a`, fetched on October 5, 2026. A filing counts only if it was filed on or before the valuation date, and every rate and price is the last observation on or before that date, so no question contains data published after its valuation date.

- [`snapshot_subset/edgar/companyfacts/`](snapshot_subset/edgar/companyfacts/): the SEC XBRL company facts (`CIK<10 digits>.json.gz`) of the 68 companies in `cases_v1_us/`. SEC EDGAR data is public.
- [`snapshot_subset/fred/`](snapshot_subset/fred/): the FRED series DTB3 (3-month bill), DGS10, DGS20 (Treasury yields) and T10YIE.
- [`snapshot_manifest/snap-2026-10-05-a.manifest.json`](snapshot_manifest/): every payload of the full snapshot (SEC, FRED, Damodaran, Yahoo Finance, the S&P 100 membership pages), with source URL, fetch time, size and SHA-256. Keys in URLs were redacted when the snapshot was written.

The Yahoo Finance price histories and Damodaran's spreadsheets are not redistributed (their terms do not clearly allow it); the cases and questions carry the derived values (the closing price on the valuation date, the industry beta, the rating spread). Without the price files, check C of the audit skips the market-value rows; checks A, B, D and E reproduce in full ([`results/README.md`](../results/README.md)).
