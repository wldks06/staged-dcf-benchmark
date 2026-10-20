# Paper tables, grading mode `plan_think`

Accuracy = final answer within tolerance. Mean +/- sd over seeds where a model was sampled three times; cells with a slash are pooled counts over seeds. Groups: single = one calculation (v2 basic L2, 56), trap (40), Half A (steps 2-3, 20), Half B (steps 4-5, 20), full textbook (28), full practitioner (20); @2019 and @2022 are the same question types for 13 firms at those valuation dates, @2025n for 5 firms not in v2.

## A. Accuracy by model and tool

| model | tool | seeds | v2 acc (184) | all acc (308) | rubric v2 | single | trap | Half A | Half B | full tb | full pr | full tb @2019 | full tb @2022 | full tb @2025n | full pr @2019 | full pr @2022 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 1 | 60.3 | 60.3 | 52.9 | 53/56 (94.6) | 36/40 (90.0) | 4/20 (20.0) | 15/20 (75.0) | 2/28 (7.1) | 1/20 (5.0) |  |  |  |  |  |
| Qwen2.5-7B-Instruct | none | 1 | 45.7 | 45.7 | 36.1 | 50/56 (89.3) | 32/40 (80.0) | 2/20 (10.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) |  |  |  |  |  |
| Qwen3-32B | none | 1 | 95.7 | 95.7 | 97.0 | 56/56 (100.0) | 40/40 (100.0) | 19/20 (95.0) | 19/20 (95.0) | 25/28 (89.3) | 17/20 (85.0) |  |  |  |  |  |
| dianjin-32b | calc | 3 | 75.2 +/- 1.3 | 65.9 +/- 1.9 | 85.1 +/- 0.5 | 163/168 (97.0) | 117/120 (97.5) | 43/60 (71.7) | 49/60 (81.7) | 25/84 (29.8) | 18/60 (30.0) | 7/39 (17.9) | 12/39 (30.8) | 6/15 (40.0) | 12/39 (30.8) | 14/39 (35.9) |
| dianjin-32b | none | 3 | 80.1 +/- 1.4 | 72.8 +/- 2.5 | 86.2 +/- 1.2 | 166/168 (98.8) | 118/120 (98.3) | 52/60 (86.7) | 56/60 (93.3) | 22/84 (26.2) | 28/60 (46.7) | 17/39 (43.6) | 11/39 (28.2) | 1/15 (6.7) | 16/39 (41.0) | 11/39 (28.2) |
| dianjin-7b | calc | 3 | 51.1 +/- 1.6 | 34.4 +/- 1.0 | 54.6 +/- 2.2 | 158/168 (94.0) | 97/120 (80.8) | 9/60 (15.0) | 14/60 (23.3) | 4/84 (4.8) | 0/60 (0.0) | 2/39 (5.1) | 0/39 (0.0) | 2/15 (13.3) | 1/39 (2.6) | 2/39 (5.1) |
| dianjin-7b | none | 3 | 50.9 +/- 2.1 | 34.5 +/- 1.9 | 54.6 +/- 2.0 | 160/168 (95.2) | 99/120 (82.5) | 3/60 (5.0) | 17/60 (28.3) | 0/84 (0.0) | 2/60 (3.3) | 5/39 (12.8) | 1/39 (2.6) | 0/15 (0.0) | 3/39 (7.7) | 3/39 (7.7) |
| fin-o1-14b | calc | 3 | 47.3 +/- 1.4 | 30.4 +/- 1.2 | 42.9 +/- 1.7 | 145/168 (86.3) | 103/120 (85.8) | 8/60 (13.3) | 3/60 (5.0) | 0/84 (0.0) | 2/60 (3.3) | 1/39 (2.6) | 0/39 (0.0) | 0/15 (0.0) | 1/39 (2.6) | 0/39 (0.0) |
| fin-o1-14b | none | 3 | 48.6 +/- 0.3 | 30.7 +/- 0.5 | 40.7 +/- 0.5 | 153/168 (91.1) | 100/120 (83.3) | 4/60 (6.7) | 5/60 (8.3) | 4/84 (4.8) | 2/60 (3.3) | 1/39 (2.6) | 1/39 (2.6) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fin-o1-8b | calc | 3 | 45.5 +/- 3.3 | 28.8 +/- 2.8 | 41.8 +/- 2.3 | 139/168 (82.7) | 97/120 (80.8) | 4/60 (6.7) | 3/60 (5.0) | 3/84 (3.6) | 5/60 (8.3) | 1/39 (2.6) | 0/39 (0.0) | 0/15 (0.0) | 1/39 (2.6) | 2/39 (5.1) |
| fin-o1-8b | none | 3 | 43.7 +/- 1.4 | 27.7 +/- 1.3 | 39.6 +/- 0.3 | 136/168 (81.0) | 92/120 (76.7) | 4/60 (6.7) | 1/60 (1.7) | 2/84 (2.4) | 6/60 (10.0) | 0/39 (0.0) | 2/39 (5.1) | 0/15 (0.0) | 1/39 (2.6) | 3/39 (7.7) |
| fin-r1 | calc | 3 | 39.7 +/- 2.0 | 25.2 +/- 2.0 | 39.7 +/- 1.4 | 122/168 (72.6) | 83/120 (69.2) | 3/60 (5.0) | 6/60 (10.0) | 2/84 (2.4) | 3/60 (5.0) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fin-r1 | none | 3 | 43.1 +/- 0.3 | 27.3 +/- 0.3 | 43.7 +/- 1.4 | 139/168 (82.7) | 89/120 (74.2) | 3/60 (5.0) | 4/60 (6.7) | 2/84 (2.4) | 1/60 (1.7) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fino1-8b | calc | 3 | 21.9 +/- 1.4 | 14.0 +/- 1.1 | 23.6 +/- 0.5 | 66/168 (39.3) | 43/120 (35.8) | 5/60 (8.3) | 2/60 (3.3) | 1/84 (1.2) | 4/60 (6.7) | 1/39 (2.6) | 0/39 (0.0) | 1/15 (6.7) | 0/39 (0.0) | 0/39 (0.0) |
| fino1-8b | none | 3 | 22.8 +/- 2.5 | 15.0 +/- 1.3 | 25.4 +/- 0.5 | 73/168 (43.5) | 45/120 (37.5) | 4/60 (6.7) | 0/60 (0.0) | 0/84 (0.0) | 4/60 (6.7) | 2/39 (5.1) | 0/39 (0.0) | 0/15 (0.0) | 4/39 (10.3) | 0/39 (0.0) |
| llama31-8b | calc | 1 | 27.2 | 16.6 | 26.7 | 31/56 (55.4) | 19/40 (47.5) | 0/20 (0.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| llama31-8b | none | 1 | 25.5 | 15.9 | 33.1 | 29/56 (51.8) | 17/40 (42.5) | 0/20 (0.0) | 0/20 (0.0) | 0/28 (0.0) | 1/20 (5.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 1/13 (7.7) | 0/13 (0.0) |
| qwen25-32b | calc | 1 | 67.4 | 56.8 | 62.9 | 53/56 (94.6) | 40/40 (100.0) | 6/20 (30.0) | 20/20 (100.0) | 4/28 (14.3) | 1/20 (5.0) | 1/13 (7.7) | 0/13 (0.0) | 1/5 (20.0) | 0/13 (0.0) | 1/13 (7.7) |
| qwen25-32b | none | 1 | 53.3 | 37.7 | 51.8 | 47/56 (83.9) | 36/40 (90.0) | 5/20 (25.0) | 10/20 (50.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| qwen25-7b | calc | 1 | 45.7 | 28.6 | 35.6 | 49/56 (87.5) | 31/40 (77.5) | 1/20 (5.0) | 2/20 (10.0) | 0/28 (0.0) | 1/20 (5.0) | 1/13 (7.7) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| qwen25-7b | none | 1 | 45.7 | 29.5 | 38.2 | 51/56 (91.1) | 29/40 (72.5) | 3/20 (15.0) | 1/20 (5.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 1/13 (7.7) |
| qwen3-14b | calc | 3 | 78.3 +/- 2.5 | 75.3 +/- 1.4 | 88.7 +/- 1.6 | 168/168 (100.0) | 119/120 (99.2) | 50/60 (83.3) | 43/60 (71.7) | 26/84 (31.0) | 26/60 (43.3) | 24/39 (61.5) | 19/39 (48.7) | 7/15 (46.7) | 22/39 (56.4) | 29/39 (74.4) |
| qwen3-14b | none | 3 | 82.6 +/- 2.9 | 80.0 +/- 2.3 | 91.1 +/- 2.1 | 168/168 (100.0) | 118/120 (98.3) | 53/60 (88.3) | 39/60 (65.0) | 40/84 (47.6) | 38/60 (63.3) | 31/39 (79.5) | 29/39 (74.4) | 8/15 (53.3) | 22/39 (56.4) | 33/39 (84.6) |
| qwen3-32b | calc | 3 | 85.3 +/- 1.4 | 82.0 +/- 2.9 | 93.9 +/- 0.4 | 166/168 (98.8) | 120/120 (100.0) | 48/60 (80.0) | 58/60 (96.7) | 47/84 (56.0) | 32/60 (53.3) | 23/39 (59.0) | 29/39 (74.4) | 9/15 (60.0) | 18/39 (46.2) | 24/39 (61.5) |
| qwen3-32b | none | 3 | 96.2 +/- 1.4 | 95.5 +/- 1.1 | 97.7 +/- 0.5 | 166/168 (98.8) | 120/120 (100.0) | 58/60 (96.7) | 60/60 (100.0) | 74/84 (88.1) | 53/60 (88.3) | 34/39 (87.2) | 37/39 (94.9) | 14/15 (93.3) | 32/39 (82.1) | 38/39 (97.4) |
| qwen3-8b | calc | 3 | 80.6 +/- 1.7 | 74.6 +/- 2.1 | 87.7 +/- 1.1 | 167/168 (99.4) | 120/120 (100.0) | 45/60 (75.0) | 57/60 (95.0) | 35/84 (41.7) | 21/60 (35.0) | 18/39 (46.2) | 15/39 (38.5) | 7/15 (46.7) | 18/39 (46.2) | 14/39 (35.9) |
| qwen3-8b | none | 3 | 77.0 +/- 1.7 | 72.7 +/- 1.2 | 85.0 +/- 1.0 | 168/168 (100.0) | 120/120 (100.0) | 41/60 (68.3) | 50/60 (83.3) | 23/84 (27.4) | 23/60 (38.3) | 22/39 (56.4) | 19/39 (48.7) | 8/15 (53.3) | 18/39 (46.2) | 22/39 (56.4) |

## B. Step scores on the v2 full textbook valuations (rubric points earned, %)

| model | tool | Step 2 | Step 3 | Step 4 | Step 5 | final (28) |
|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 41.7 | 32.6 | 31.0 | 17.9 | 2/28 |
| Qwen2.5-7B-Instruct | none | 26.8 | 24.6 | 21.3 | 7.1 | 0/28 |
| Qwen3-32B | none | 98.4 | 98.6 | 98.4 | 92.9 | 25/28 |
| dianjin-32b | calc | 96.1 | 94.2 | 74.6 | 51.2 | 25/84 |
| dianjin-32b | none | 96.1 | 93.7 | 70.0 | 44.0 | 22/84 |
| dianjin-7b | calc | 49.1 | 53.9 | 46.7 | 17.9 | 4/84 |
| dianjin-7b | none | 48.8 | 52.2 | 45.2 | 15.5 | 0/84 |
| fin-o1-14b | calc | 48.8 | 40.1 | 33.7 | 14.3 | 0/84 |
| fin-o1-14b | none | 42.3 | 34.1 | 28.5 | 11.9 | 4/84 |
| fin-o1-8b | calc | 39.1 | 38.4 | 31.7 | 13.1 | 3/84 |
| fin-o1-8b | none | 35.7 | 36.7 | 30.6 | 14.3 | 2/84 |
| fin-r1 | calc | 26.8 | 30.4 | 26.8 | 7.1 | 2/84 |
| fin-r1 | none | 32.8 | 36.7 | 32.5 | 6.0 | 2/84 |
| fino1-8b | calc | 24.1 | 21.7 | 17.2 | 4.8 | 1/84 |
| fino1-8b | none | 19.4 | 28.3 | 19.6 | 4.8 | 0/84 |
| llama31-8b | calc | 36.2 | 21.0 | 16.4 | 3.6 | 0/28 |
| llama31-8b | none | 20.5 | 35.5 | 33.0 | 3.6 | 0/28 |
| qwen25-32b | calc | 50.4 | 37.0 | 53.1 | 25.0 | 4/28 |
| qwen25-32b | none | 52.8 | 48.6 | 39.9 | 17.9 | 0/28 |
| qwen25-7b | calc | 28.3 | 24.6 | 20.4 | 7.1 | 0/28 |
| qwen25-7b | none | 22.0 | 29.0 | 19.6 | 17.9 | 0/28 |
| qwen3-14b | calc | 100.0 | 96.6 | 84.4 | 60.7 | 26/84 |
| qwen3-14b | none | 100.0 | 96.9 | 87.7 | 63.1 | 40/84 |
| qwen3-32b | calc | 99.0 | 98.8 | 97.1 | 95.2 | 47/84 |
| qwen3-32b | none | 99.2 | 98.3 | 97.0 | 91.7 | 74/84 |
| qwen3-8b | calc | 99.5 | 96.1 | 79.2 | 59.5 | 35/84 |
| qwen3-8b | none | 97.4 | 91.3 | 75.9 | 50.0 | 23/84 |

## C. Chain gap and trap falls (pooled over seeds)

Chain gap cells: firms with both halves correct / firms with both halves and a full valuation, then how many of those firms still failed the full textbook valuation.

| model | tool | v2 2025 (20 firms) | 2019 (13) | 2022 (13) | new 2025 (5) | trap falls |
|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 4/20 both ok, 4 full wrong |  |  |  | 0/42 |
| Qwen2.5-7B-Instruct | none | 0/20 both ok, 0 full wrong |  |  |  | 3/42 |
| Qwen3-32B | none | 18/20 both ok, 1 full wrong |  |  |  | 0/42 |
| dianjin-32b | calc | 35/60 both ok, 24 full wrong | 21/39 both ok, 16 full wrong | 17/39 both ok, 11 full wrong | 10/15 both ok, 7 full wrong | 1/126 |
| dianjin-32b | none | 49/60 both ok, 39 full wrong | 34/39 both ok, 20 full wrong | 28/39 both ok, 22 full wrong | 14/15 both ok, 13 full wrong | 0/126 |
| dianjin-7b | calc | 1/60 both ok, 1 full wrong | 1/39 both ok, 1 full wrong | 1/39 both ok, 1 full wrong | 0/15 both ok, 0 full wrong | 11/126 |
| dianjin-7b | none | 1/60 both ok, 1 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 1/15 both ok, 1 full wrong | 12/126 |
| fin-o1-14b | calc | 0/60 both ok, 0 full wrong | 1/39 both ok, 1 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 10/126 |
| fin-o1-14b | none | 1/60 both ok, 1 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 9/126 |
| fin-o1-8b | calc | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 8/126 |
| fin-o1-8b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 1/39 both ok, 1 full wrong | 0/15 both ok, 0 full wrong | 9/126 |
| fin-r1 | calc | 1/60 both ok, 1 full wrong | 1/39 both ok, 1 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 11/126 |
| fin-r1 | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 1/39 both ok, 1 full wrong | 0/15 both ok, 0 full wrong | 12/126 |
| fino1-8b | calc | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 12/126 |
| fino1-8b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 11/126 |
| llama31-8b | calc | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 4/42 |
| llama31-8b | none | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 2/42 |
| qwen25-32b | calc | 6/20 both ok, 5 full wrong | 7/13 both ok, 6 full wrong | 7/13 both ok, 7 full wrong | 3/5 both ok, 2 full wrong | 0/42 |
| qwen25-32b | none | 2/20 both ok, 2 full wrong | 1/13 both ok, 1 full wrong | 1/13 both ok, 1 full wrong | 0/5 both ok, 0 full wrong | 1/42 |
| qwen25-7b | calc | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 1/42 |
| qwen25-7b | none | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 4/42 |
| qwen3-14b | calc | 34/60 both ok, 27 full wrong | 27/39 both ok, 11 full wrong | 26/39 both ok, 14 full wrong | 11/15 both ok, 4 full wrong | 1/126 |
| qwen3-14b | none | 36/60 both ok, 19 full wrong | 20/39 both ok, 5 full wrong | 28/39 both ok, 8 full wrong | 11/15 both ok, 6 full wrong | 2/126 |
| qwen3-32b | calc | 46/60 both ok, 18 full wrong | 34/39 both ok, 13 full wrong | 35/39 both ok, 9 full wrong | 15/15 both ok, 6 full wrong | 0/126 |
| qwen3-32b | none | 58/60 both ok, 10 full wrong | 38/39 both ok, 5 full wrong | 37/39 both ok, 1 full wrong | 14/15 both ok, 1 full wrong | 0/126 |
| qwen3-8b | calc | 43/60 both ok, 27 full wrong | 35/39 both ok, 17 full wrong | 29/39 both ok, 17 full wrong | 10/15 both ok, 5 full wrong | 0/126 |
| qwen3-8b | none | 35/60 both ok, 27 full wrong | 28/39 both ok, 10 full wrong | 25/39 both ok, 13 full wrong | 12/15 both ok, 6 full wrong | 0/126 |
