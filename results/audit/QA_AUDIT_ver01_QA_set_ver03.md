# QA audit ver01: QA_set_ver03

Questions: 104. Rubric rows: 1690. Source cases: data/cases_v1_us/cases.jsonl.

| Check | Result |
|---|---|
| A. Answer key vs independent engine | match: 1586 |
| B. Reproducible from the question text | ok: 104 |
| C. Inputs vs raw SEC / FRED / price files | match: 1215, match after undoing later split/spin-off factor 1.067: 2, match after undoing later split/spin-off factor 15: 2, match after undoing later split/spin-off factor 25: 1, match after undoing later split/spin-off factor 1.048: 1, match after undoing later split/spin-off factor 3: 1 |
| D. Rubric consistency (non-ok only) | target already printed in the prompt = INFO: 49, alternative value separated from the correct answer = CLOSE (within 2x tolerance): 27, alternative value separated from the correct answer = OVERLAPS correct answer: 18, scored item has zero target = INFO: 9 |
| E. Cases outside the 0.3x-3x band | 0 of 52 |

Details per row are in the CSV files next to this report.

## A: rows that need a look (0)

None.

## B: rows that need a look (0)

None.

## C: rows that need a look (0)

None.

## D: rows that need a look (45)

| question_id | tier | level | check | status | detail |
|---|---|---|---|---|---|
| CMCSA-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.7043 vs tolerance 0.5766 / Alternative, not scored: value per share on the latest ba |
| CMCSA-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.7043 vs tolerance 0.5766 / Alternative, not scored: value per share on the latest ba |
| CMCSA-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.325 vs tolerance 1.084 / Alternative, not scored: value per share on the latest basi |
| PM-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0142 vs tolerance 0.5329 / Alternative, not scored: value per share on the latest ba |
| PM-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0142 vs tolerance 0.5329 / Alternative, not scored: value per share on the latest ba |
| PM-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0279 vs tolerance 1.044 / Alternative, not scored: value per share on the latest bas |
| PPL-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.627 vs tolerance 0.9525 / Alternative, not scored: value per share on the latest bas |
| PPL-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.627 vs tolerance 0.9525 / Alternative, not scored: value per share on the latest bas |
| PPL-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.429 vs tolerance 1.422 / Alternative, not scored: value per share on the latest basi |
| META-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.263 vs tolerance 1.177 / Alternative, not scored: value per share on the latest basi |
| META-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.263 vs tolerance 1.177 / Alternative, not scored: value per share on the latest basi |
| META-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.027 vs tolerance 1.889 / Alternative, not scored: value per share on the latest basi |
| VZ-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.001 vs tolerance 0.9779 / Alternative, not scored: value per share on the latest bas |
| VZ-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.001 vs tolerance 0.9779 / Alternative, not scored: value per share on the latest bas |
| VZ-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0018 vs tolerance 1.62 / Alternative, not scored: value per share on the latest basi |
| PEP-2019-05 | basic@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.93 vs tolerance 0.6431 / Alternative, not scored: value per share on the latest basi |
| PEP-2019-07 | half@2019 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.93 vs tolerance 0.6431 / Alternative, not scored: value per share on the latest basi |
| PEP-2019-08 | complex@2019 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.683 vs tolerance 1.164 / Alternative, not scored: value per share on the latest basi |
| CMCSA-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.5779 vs tolerance 0.3784 / Alternative, not scored: value per share on the latest ba |
| CMCSA-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.5779 vs tolerance 0.3784 / Alternative, not scored: value per share on the latest ba |
| CMCSA-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.9703 vs tolerance 0.6355 / Alternative, not scored: value per share on the latest ba |
| PM-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1773 vs tolerance 0.2997 / Alternative, not scored: value per share on the latest ba |
| PM-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1773 vs tolerance 0.2997 / Alternative, not scored: value per share on the latest ba |
| PM-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3722 vs tolerance 0.6289 / Alternative, not scored: value per share on the latest ba |
| WMB-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0285 vs tolerance 0.1323 / Alternative, not scored: value per share on the latest ba |
| WMB-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0285 vs tolerance 0.1323 / Alternative, not scored: value per share on the latest ba |
| WMB-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.0562 vs tolerance 0.2606 / Alternative, not scored: value per share on the latest ba |
| JNJ-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.189 vs tolerance 0.699 / Alternative, not scored: value per share on the latest basi |
| JNJ-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.189 vs tolerance 0.699 / Alternative, not scored: value per share on the latest basi |
| JNJ-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.888 vs tolerance 1.11 / Alternative, not scored: value per share on the latest basic |
| META-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.112 vs tolerance 1.351 / Alternative, not scored: value per share on the latest basi |
| META-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 2.112 vs tolerance 1.351 / Alternative, not scored: value per share on the latest basi |
| META-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 3.483 vs tolerance 2.229 / Alternative, not scored: value per share on the latest basi |
| VZ-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8271 vs tolerance 0.726 / Alternative, not scored: value per share on the latest bas |
| VZ-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.8271 vs tolerance 0.726 / Alternative, not scored: value per share on the latest bas |
| VZ-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.404 vs tolerance 1.232 / Alternative, not scored: value per share on the latest basi |
| MCD-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.5461 vs tolerance 0.4942 / Alternative, not scored: value per share on the latest ba |
| MCD-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 0.5461 vs tolerance 0.4942 / Alternative, not scored: value per share on the latest ba |
| MCD-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | CLOSE (within 2x tolerance) | gap 1.279 vs tolerance 1.158 / Alternative, not scored: value per share on the latest basi |
| PEP-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1751 vs tolerance 0.4367 / Alternative, not scored: value per share on the latest ba |
| PEP-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1751 vs tolerance 0.4367 / Alternative, not scored: value per share on the latest ba |
| PEP-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.3496 vs tolerance 0.8717 / Alternative, not scored: value per share on the latest ba |
| MRK-2022-05 | basic@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1156 vs tolerance 0.2847 / Alternative, not scored: value per share on the latest ba |
| MRK-2022-07 | half@2022 | 5 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.1156 vs tolerance 0.2847 / Alternative, not scored: value per share on the latest ba |
| MRK-2022-08 | complex@2022 | 3 | alternative value separated from the correct answer | OVERLAPS correct answer | gap 0.2121 vs tolerance 0.5223 / Alternative, not scored: value per share on the latest ba |
