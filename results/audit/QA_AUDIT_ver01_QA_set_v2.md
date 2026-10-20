# QA audit ver01: QA_set_v2

Questions: 200. Rubric rows: 2348. Source cases: data/cases_v1_us/cases.jsonl.

| Check | Result |
|---|---|
| A. Answer key vs independent engine | match: 2106 |
| B. Reproducible from the question text | ok: 184 |
| C. Inputs vs raw SEC / FRED / price files | match: 1320, match after undoing later split/spin-off factor 25: 1, match after undoing later split/spin-off factor 1.067: 1, match after undoing later split/spin-off factor 2: 1, match after undoing later split/spin-off factor 1.03: 1 |
| D. Rubric consistency (non-ok only) | target already printed in the prompt = INFO: 40, alternative value separated from the correct answer = OVERLAPS correct answer: 33, scored item has zero target = INFO: 26, alternative value separated from the correct answer = CLOSE (within 2x tolerance): 15, trap value separated from the correct answer = CLOSE (within 2x tolerance): 2 |
| E. Cases outside the 0.3x-3x band | 0 of 48 |

Details per row are in the CSV files next to this report.

## A: rows that need a look (0)

None.

## B: rows that need a look (0)

None.

## C: rows that need a look (0)

None.

## D: rows that need a look (50)

| question_id | tier | level | check | status | detail |
|---|---|---|---|---|---|
| VZ-02 | basic | 2 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.2476 vs tolerance 0.7839 / Alternative, not scored: value per share on the latest ba |
| VZ-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.2476 vs tolerance 0.7839 / Alternative, not scored: value per share on the latest ba |
| MCD-03 | basic | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.38 vs tolerance 1.325 / Alternative, not scored: value per share on the latest basic |
| PEP-01 | basic | 2 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.4903 vs tolerance 1.035 / Alternative, not scored: value per share on the latest bas |
| PEP-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.4903 vs tolerance 1.035 / Alternative, not scored: value per share on the latest bas |
| MRK-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3054 vs tolerance 0.5157 / Alternative, not scored: value per share on the latest ba |
| SHW-01 | basic | 2 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.158 vs tolerance 1.064 / Alternative, not scored: value per share on the latest basi |
| SHW-03 | basic | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.158 vs tolerance 1.064 / Alternative, not scored: value per share on the latest basi |
| CEG-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.815 vs tolerance 1.184 / Alternative, not scored: value per share on the latest basi |
| WEC-02 | basic | 2 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3361 vs tolerance 0.8529 / Alternative, not scored: value per share on the latest ba |
| WEC-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3361 vs tolerance 0.8529 / Alternative, not scored: value per share on the latest ba |
| XOM-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 2.828 vs tolerance 2.839 / Alternative, not scored: value per share on the latest basi |
| MELI-03 | basic | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0009 vs tolerance 8.224 / Alternative, not scored: value per share on the latest bas |
| ETN-03 | basic | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.548 vs tolerance 0.8199 / Alternative, not scored: value per share on the latest bas |
| GE-03 | basic | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.814 vs tolerance 0.9401 / Alternative, not scored: value per share on the latest bas |
| SCCO-01 | basic | 2 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.292 vs tolerance 0.6516 / Alternative, not scored: value per share on the latest bas |
| SCCO-03 | basic | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.292 vs tolerance 0.6516 / Alternative, not scored: value per share on the latest bas |
| CMCSA-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.4747 vs tolerance 0.8017 / Alternative, not scored: value per share on the latest ba |
| PM-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0742 vs tolerance 1.01 / Alternative, not scored: value per share on the latest basi |
| WMB-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0568 vs tolerance 0.1934 / Alternative, not scored: value per share on the latest ba |
| JNJ-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.7462 vs tolerance 0.8248 / Alternative, not scored: value per share on the latest ba |
| UNP-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.7936 vs tolerance 1.112 / Alternative, not scored: value per share on the latest bas |
| CRH-07 | half | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8045 vs tolerance 0.4178 / Alternative, not scored: value per share on the latest ba |
| PPL-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0377 vs tolerance 0.1786 / Alternative, not scored: value per share on the latest ba |
| VZ-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.2476 vs tolerance 0.7839 / Alternative, not scored: value per share on the latest ba |
| MCD-07 | half | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.38 vs tolerance 1.325 / Alternative, not scored: value per share on the latest basic |
| PEP-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.4903 vs tolerance 1.035 / Alternative, not scored: value per share on the latest bas |
| MRK-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3054 vs tolerance 0.5157 / Alternative, not scored: value per share on the latest ba |
| SHW-07 | half | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.158 vs tolerance 1.064 / Alternative, not scored: value per share on the latest basi |
| CEG-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.815 vs tolerance 1.184 / Alternative, not scored: value per share on the latest basi |
| WEC-07 | half | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3361 vs tolerance 0.8529 / Alternative, not scored: value per share on the latest ba |
| CRH-11 | trap | 2 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8045 vs tolerance 0.4178 / Alternative, not scored: value per share on the latest ba |
| PEP-11 | trap | 2 | trap value separated from the correct answer | CLOSE (within 2x tolerance) | gap 4116 vs tolerance 2099 / Fell for the trap (Gordon formula on the final-year cash flow |
| CVX-11 | trap | 2 | trap value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.585e+04 vs tolerance 8084 / Fell for the trap (Gordon formula on the final-year cash |
| SHW-11 | trap | 2 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.158 vs tolerance 1.064 / Alternative, not scored: value per share on the latest basi |
| WEC-11 | trap | 2 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3361 vs tolerance 0.8529 / Alternative, not scored: value per share on the latest ba |
| CMCSA-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.5573 vs tolerance 0.9414 / Alternative, not scored: value per share on the latest ba |
| PM-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0946 vs tolerance 1.288 / Alternative, not scored: value per share on the latest bas |
| WMB-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.073 vs tolerance 0.2483 / Alternative, not scored: value per share on the latest bas |
| JNJ-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.9846 vs tolerance 1.088 / Alternative, not scored: value per share on the latest bas |
| UNP-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 1.149 vs tolerance 1.61 / Alternative, not scored: value per share on the latest basic |
| CRH-08 | complex | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.226 vs tolerance 0.6369 / Alternative, not scored: value per share on the latest bas |
| PPL-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0431 vs tolerance 0.2043 / Alternative, not scored: value per share on the latest ba |
| VZ-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3089 vs tolerance 0.978 / Alternative, not scored: value per share on the latest bas |
| MCD-08 | complex | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.984 vs tolerance 1.905 / Alternative, not scored: value per share on the latest basi |
| PEP-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.5925 vs tolerance 1.25 / Alternative, not scored: value per share on the latest basi |
| MRK-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.4 vs tolerance 0.6753 / Alternative, not scored: value per share on the latest basic |
| SHW-08 | complex | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.602 vs tolerance 1.472 / Alternative, not scored: value per share on the latest basi |
| CEG-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.7063 vs tolerance 1.026 / Alternative, not scored: value per share on the latest bas |
| WEC-08 | complex | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.2645 vs tolerance 0.6714 / Alternative, not scored: value per share on the latest ba |
