# QA audit ver01: QA_set_ver03_newco

Questions: 20. Rubric rows: 325. Source cases: data/cases_v1_us/cases.jsonl.

| Check | Result |
|---|---|
| A. Answer key vs independent engine | match: 305 |
| B. Reproducible from the question text | ok: 20 |
| C. Inputs vs raw SEC / FRED / price files | match: 233 |
| D. Rubric consistency (non-ok only) | target already printed in the prompt = INFO: 8, alternative value separated from the correct answer = CLOSE (within 2x tolerance): 6, scored item has zero target = INFO: 6, alternative value separated from the correct answer = OVERLAPS correct answer: 3 |
| E. Cases outside the 0.3x-3x band | 0 of 10 |

Details per row are in the CSV files next to this report.

## A: rows that need a look (0)

None.

## B: rows that need a look (0)

None.

## C: rows that need a look (0)

None.

## D: rows that need a look (9)

| question_id | tier | level | check | status | detail |
|---|---|---|---|---|---|
| ECL-2025-05 | basic@2025 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8541 vs tolerance 0.6709 / Alternative, not scored: value per share on the latest ba |
| ECL-2025-07 | half@2025 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8541 vs tolerance 0.6709 / Alternative, not scored: value per share on the latest ba |
| ECL-2025-08 | complex@2025 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.147 vs tolerance 0.9008 / Alternative, not scored: value per share on the latest bas |
| KO-2025-05 | basic@2025 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1406 vs tolerance 0.3185 / Alternative, not scored: value per share on the latest ba |
| KO-2025-07 | half@2025 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1406 vs tolerance 0.3185 / Alternative, not scored: value per share on the latest ba |
| KO-2025-08 | complex@2025 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1652 vs tolerance 0.3739 / Alternative, not scored: value per share on the latest ba |
| LIN-2025-05 | basic@2025 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.427 vs tolerance 1.25 / Alternative, not scored: value per share on the latest basic |
| LIN-2025-07 | half@2025 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.427 vs tolerance 1.25 / Alternative, not scored: value per share on the latest basic |
| LIN-2025-08 | complex@2025 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 3.194 vs tolerance 1.645 / Alternative, not scored: value per share on the latest basi |
