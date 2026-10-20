# Paper tables, grading mode `qa`

Accuracy = final answer within tolerance. Mean +/- sd over seeds where a model was sampled three times; cells with a slash are pooled counts over seeds. Groups: single = one calculation (v2 basic L2, 56), trap (40), Half A (steps 2-3, 20), Half B (steps 4-5, 20), full textbook (28), full practitioner (20); @2019 and @2022 are the same question types for 13 firms at those valuation dates, @2025n for 5 firms not in v2.

## A. Accuracy by model and tool

| model | tool | seeds | v2 acc (184) | all acc (308) | rubric v2 | single | trap | Half A | Half B | full tb | full pr | full tb @2019 | full tb @2022 | full tb @2025n | full pr @2019 | full pr @2022 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 1 | 58.7 | 58.7 | 45.4 | 53/56 (94.6) | 36/40 (90.0) | 4/20 (20.0) | 12/20 (60.0) | 2/28 (7.1) | 1/20 (5.0) |  |  |  |  |  |
| Qwen2.5-7B-Instruct | none | 1 | 40.2 | 40.2 | 28.3 | 43/56 (76.8) | 29/40 (72.5) | 2/20 (10.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) |  |  |  |  |  |
| Qwen3-32B | none | 1 | 91.3 | 91.3 | 83.7 | 53/56 (94.6) | 40/40 (100.0) | 19/20 (95.0) | 19/20 (95.0) | 23/28 (82.1) | 14/20 (70.0) |  |  |  |  |  |
| dianjin-32b | calc | 3 | 70.5 +/- 2.6 | 61.4 +/- 2.3 | 65.3 +/- 1.2 | 152/168 (90.5) | 117/120 (97.5) | 43/60 (71.7) | 48/60 (80.0) | 16/84 (19.0) | 13/60 (21.7) | 5/39 (12.8) | 11/39 (28.2) | 3/15 (20.0) | 11/39 (28.2) | 10/39 (25.6) |
| dianjin-32b | none | 3 | 75.5 +/- 2.0 | 66.8 +/- 2.5 | 64.6 +/- 1.4 | 164/168 (97.6) | 118/120 (98.3) | 52/60 (86.7) | 51/60 (85.0) | 14/84 (16.7) | 18/60 (30.0) | 12/39 (30.8) | 7/39 (17.9) | 1/15 (6.7) | 9/39 (23.1) | 6/39 (15.4) |
| dianjin-7b | calc | 3 | 47.6 +/- 0.3 | 31.7 +/- 0.7 | 27.8 +/- 1.5 | 142/168 (84.5) | 97/120 (80.8) | 9/60 (15.0) | 12/60 (20.0) | 3/84 (3.6) | 0/60 (0.0) | 1/39 (2.6) | 0/39 (0.0) | 1/15 (6.7) | 1/39 (2.6) | 0/39 (0.0) |
| dianjin-7b | none | 3 | 46.6 +/- 3.5 | 30.5 +/- 2.2 | 28.5 +/- 2.5 | 148/168 (88.1) | 94/120 (78.3) | 3/60 (5.0) | 12/60 (20.0) | 0/84 (0.0) | 0/60 (0.0) | 2/39 (5.1) | 1/39 (2.6) | 0/15 (0.0) | 2/39 (5.1) | 1/39 (2.6) |
| fin-o1-14b | calc | 3 | 38.6 +/- 2.8 | 25.0 +/- 1.7 | 33.5 +/- 1.8 | 108/168 (64.3) | 94/120 (78.3) | 8/60 (13.3) | 3/60 (5.0) | 0/84 (0.0) | 0/60 (0.0) | 1/39 (2.6) | 0/39 (0.0) | 0/15 (0.0) | 1/39 (2.6) | 0/39 (0.0) |
| fin-o1-14b | none | 3 | 39.7 +/- 2.0 | 25.2 +/- 1.6 | 31.1 +/- 0.6 | 117/168 (69.6) | 92/120 (76.7) | 4/60 (6.7) | 3/60 (5.0) | 3/84 (3.6) | 0/60 (0.0) | 1/39 (2.6) | 1/39 (2.6) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fin-o1-8b | calc | 3 | 35.9 +/- 2.7 | 22.5 +/- 2.2 | 32.2 +/- 2.1 | 100/168 (59.5) | 86/120 (71.7) | 4/60 (6.7) | 3/60 (5.0) | 2/84 (2.4) | 3/60 (5.0) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 0/39 (0.0) | 2/39 (5.1) |
| fin-o1-8b | none | 3 | 33.7 +/- 1.4 | 21.4 +/- 0.9 | 30.0 +/- 0.7 | 98/168 (58.3) | 80/120 (66.7) | 4/60 (6.7) | 1/60 (1.7) | 1/84 (1.2) | 2/60 (3.3) | 0/39 (0.0) | 1/39 (2.6) | 0/15 (0.0) | 0/39 (0.0) | 3/39 (7.7) |
| fin-r1 | calc | 3 | 29.7 +/- 2.8 | 18.9 +/- 2.1 | 23.7 +/- 0.7 | 84/168 (50.0) | 70/120 (58.3) | 3/60 (5.0) | 4/60 (6.7) | 1/84 (1.2) | 2/60 (3.3) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fin-r1 | none | 3 | 33.7 +/- 2.5 | 21.2 +/- 1.6 | 29.3 +/- 1.3 | 101/168 (60.1) | 78/120 (65.0) | 3/60 (5.0) | 2/60 (3.3) | 2/84 (2.4) | 0/60 (0.0) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 0/39 (0.0) | 0/39 (0.0) |
| fino1-8b | calc | 3 | 15.2 +/- 2.2 | 10.0 +/- 1.5 | 16.5 +/- 0.1 | 42/168 (25.0) | 35/120 (29.2) | 5/60 (8.3) | 1/60 (1.7) | 1/84 (1.2) | 0/60 (0.0) | 1/39 (2.6) | 0/39 (0.0) | 1/15 (6.7) | 0/39 (0.0) | 0/39 (0.0) |
| fino1-8b | none | 3 | 15.4 +/- 2.7 | 10.0 +/- 1.5 | 17.8 +/- 1.0 | 48/168 (28.6) | 32/120 (26.7) | 4/60 (6.7) | 0/60 (0.0) | 0/84 (0.0) | 1/60 (1.7) | 0/39 (0.0) | 0/39 (0.0) | 0/15 (0.0) | 1/39 (2.6) | 0/39 (0.0) |
| llama31-8b | calc | 1 | 20.1 | 12.3 | 18.9 | 20/56 (35.7) | 17/40 (42.5) | 0/20 (0.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| llama31-8b | none | 1 | 15.8 | 9.7 | 22.2 | 19/56 (33.9) | 10/40 (25.0) | 0/20 (0.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 1/13 (7.7) | 0/13 (0.0) |
| qwen25-32b | calc | 1 | 66.8 | 56.5 | 56.6 | 53/56 (94.6) | 40/40 (100.0) | 6/20 (30.0) | 20/20 (100.0) | 4/28 (14.3) | 0/20 (0.0) | 1/13 (7.7) | 0/13 (0.0) | 1/5 (20.0) | 0/13 (0.0) | 1/13 (7.7) |
| qwen25-32b | none | 1 | 49.5 | 34.4 | 43.1 | 45/56 (80.4) | 36/40 (90.0) | 5/20 (25.0) | 5/20 (25.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| qwen25-7b | calc | 1 | 42.4 | 26.3 | 29.5 | 45/56 (80.4) | 31/40 (77.5) | 1/20 (5.0) | 1/20 (5.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| qwen25-7b | none | 1 | 39.7 | 25.6 | 30.0 | 44/56 (78.6) | 26/40 (65.0) | 3/20 (15.0) | 0/20 (0.0) | 0/28 (0.0) | 0/20 (0.0) | 0/13 (0.0) | 0/13 (0.0) | 0/5 (0.0) | 0/13 (0.0) | 0/13 (0.0) |
| qwen3-14b | calc | 3 | 73.4 +/- 2.4 | 71.5 +/- 1.9 | 74.5 +/- 2.3 | 152/168 (90.5) | 119/120 (99.2) | 50/60 (83.3) | 43/60 (71.7) | 20/84 (23.8) | 21/60 (35.0) | 22/39 (56.4) | 18/39 (46.2) | 7/15 (46.7) | 21/39 (53.8) | 25/39 (64.1) |
| qwen3-14b | none | 3 | 78.3 +/- 2.5 | 75.6 +/- 1.6 | 72.2 +/- 1.7 | 164/168 (97.6) | 118/120 (98.3) | 53/60 (88.3) | 37/60 (61.7) | 28/84 (33.3) | 32/60 (53.3) | 29/39 (74.4) | 26/39 (66.7) | 8/15 (53.3) | 19/39 (48.7) | 29/39 (74.4) |
| qwen3-32b | calc | 3 | 80.8 +/- 1.4 | 79.0 +/- 3.1 | 84.7 +/- 0.7 | 145/168 (86.3) | 120/120 (100.0) | 48/60 (80.0) | 58/60 (96.7) | 45/84 (53.6) | 30/60 (50.0) | 23/39 (59.0) | 28/39 (71.8) | 8/15 (53.3) | 17/39 (43.6) | 24/39 (61.5) |
| qwen3-32b | none | 3 | 91.5 +/- 2.2 | 91.7 +/- 1.6 | 85.5 +/- 1.4 | 150/168 (89.3) | 120/120 (100.0) | 58/60 (96.7) | 55/60 (91.7) | 72/84 (85.7) | 50/60 (83.3) | 34/39 (87.2) | 37/39 (94.9) | 14/15 (93.3) | 31/39 (79.5) | 35/39 (89.7) |
| qwen3-8b | calc | 3 | 75.0 +/- 2.4 | 70.2 +/- 2.5 | 67.5 +/- 2.5 | 149/168 (88.7) | 120/120 (100.0) | 45/60 (75.0) | 55/60 (91.7) | 28/84 (33.3) | 17/60 (28.3) | 16/39 (41.0) | 14/39 (35.9) | 5/15 (33.3) | 16/39 (41.0) | 14/39 (35.9) |
| qwen3-8b | none | 3 | 70.3 +/- 0.3 | 66.9 +/- 1.6 | 61.9 +/- 1.8 | 152/168 (90.5) | 120/120 (100.0) | 41/60 (68.3) | 46/60 (76.7) | 13/84 (15.5) | 16/60 (26.7) | 19/39 (48.7) | 18/39 (46.2) | 6/15 (40.0) | 15/39 (38.5) | 18/39 (46.2) |

## B. Step scores on the v2 full textbook valuations (rubric points earned, %)

| model | tool | Step 2 | Step 3 | Step 4 | Step 5 | final (28) |
|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 11.8 | 32.6 | 16.5 | 10.7 | 2/28 |
| Qwen2.5-7B-Instruct | none | 3.9 | 24.6 | 10.4 | 3.6 | 0/28 |
| Qwen3-32B | none | 44.1 | 95.7 | 73.1 | 82.1 | 23/28 |
| dianjin-32b | calc | 3.9 | 80.7 | 30.8 | 23.8 | 16/84 |
| dianjin-32b | none | 0.0 | 77.8 | 26.1 | 20.2 | 14/84 |
| dianjin-7b | calc | 0.5 | 16.4 | 6.3 | 6.0 | 3/84 |
| dianjin-7b | none | 0.5 | 12.3 | 5.7 | 1.2 | 0/84 |
| fin-o1-14b | calc | 19.7 | 40.1 | 16.3 | 7.1 | 0/84 |
| fin-o1-14b | none | 14.7 | 34.1 | 12.4 | 10.7 | 3/84 |
| fin-o1-8b | calc | 17.3 | 38.4 | 15.3 | 6.0 | 2/84 |
| fin-o1-8b | none | 13.9 | 36.7 | 13.7 | 8.3 | 1/84 |
| fin-r1 | calc | 2.9 | 18.8 | 7.5 | 2.4 | 1/84 |
| fin-r1 | none | 3.7 | 29.2 | 11.9 | 1.2 | 2/84 |
| fino1-8b | calc | 3.9 | 21.7 | 7.7 | 4.8 | 1/84 |
| fino1-8b | none | 3.7 | 28.3 | 8.6 | 3.6 | 0/84 |
| llama31-8b | calc | 11.0 | 21.0 | 6.4 | 3.6 | 0/28 |
| llama31-8b | none | 0.0 | 35.5 | 15.9 | 0.0 | 0/28 |
| qwen25-32b | calc | 25.2 | 37.0 | 36.3 | 21.4 | 4/28 |
| qwen25-32b | none | 18.1 | 48.6 | 20.9 | 10.7 | 0/28 |
| qwen25-7b | calc | 10.2 | 24.6 | 10.0 | 7.1 | 0/28 |
| qwen25-7b | none | 2.4 | 29.0 | 10.4 | 7.1 | 0/28 |
| qwen3-14b | calc | 45.9 | 84.1 | 51.8 | 32.1 | 20/84 |
| qwen3-14b | none | 0.0 | 86.5 | 46.5 | 36.9 | 28/84 |
| qwen3-32b | calc | 77.7 | 91.5 | 78.7 | 78.6 | 45/84 |
| qwen3-32b | none | 44.6 | 96.4 | 74.1 | 86.9 | 72/84 |
| qwen3-8b | calc | 3.1 | 83.3 | 39.0 | 34.5 | 28/84 |
| qwen3-8b | none | 0.0 | 72.7 | 30.4 | 15.5 | 13/84 |

## C. Chain gap and trap falls (pooled over seeds)

Chain gap cells: firms with both halves correct / firms with both halves and a full valuation, then how many of those firms still failed the full textbook valuation.

| model | tool | v2 2025 (20 firms) | 2019 (13) | 2022 (13) | new 2025 (5) | trap falls |
|---|---|---|---|---|---|---|
| Qwen2.5-32B-Instruct | none | 4/20 both ok, 4 full wrong |  |  |  | 0/42 |
| Qwen2.5-7B-Instruct | none | 0/20 both ok, 0 full wrong |  |  |  | 3/42 |
| Qwen3-32B | none | 18/20 both ok, 3 full wrong |  |  |  | 0/42 |
| dianjin-32b | calc | 35/60 both ok, 28 full wrong | 20/39 both ok, 17 full wrong | 16/39 both ok, 10 full wrong | 9/15 both ok, 7 full wrong | 1/126 |
| dianjin-32b | none | 44/60 both ok, 41 full wrong | 30/39 both ok, 18 full wrong | 25/39 both ok, 21 full wrong | 12/15 both ok, 11 full wrong | 0/126 |
| dianjin-7b | calc | 0/60 both ok, 0 full wrong | 1/39 both ok, 1 full wrong | 1/39 both ok, 1 full wrong | 0/15 both ok, 0 full wrong | 10/126 |
| dianjin-7b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 13/126 |
| fin-o1-14b | calc | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 13/126 |
| fin-o1-14b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 13/126 |
| fin-o1-8b | calc | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 13/126 |
| fin-o1-8b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 14/126 |
| fin-r1 | calc | 1/60 both ok, 1 full wrong | 1/39 both ok, 1 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 12/126 |
| fin-r1 | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 14/126 |
| fino1-8b | calc | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 12/126 |
| fino1-8b | none | 0/60 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/39 both ok, 0 full wrong | 0/15 both ok, 0 full wrong | 11/126 |
| llama31-8b | calc | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 5/42 |
| llama31-8b | none | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 2/42 |
| qwen25-32b | calc | 6/20 both ok, 5 full wrong | 7/13 both ok, 6 full wrong | 7/13 both ok, 7 full wrong | 3/5 both ok, 2 full wrong | 0/42 |
| qwen25-32b | none | 2/20 both ok, 2 full wrong | 1/13 both ok, 1 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 1/42 |
| qwen25-7b | calc | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 1/42 |
| qwen25-7b | none | 0/20 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/13 both ok, 0 full wrong | 0/5 both ok, 0 full wrong | 4/42 |
| qwen3-14b | calc | 34/60 both ok, 28 full wrong | 27/39 both ok, 12 full wrong | 26/39 both ok, 15 full wrong | 11/15 both ok, 4 full wrong | 1/126 |
| qwen3-14b | none | 34/60 both ok, 24 full wrong | 18/39 both ok, 5 full wrong | 27/39 both ok, 11 full wrong | 10/15 both ok, 5 full wrong | 1/126 |
| qwen3-32b | calc | 46/60 both ok, 20 full wrong | 34/39 both ok, 13 full wrong | 35/39 both ok, 10 full wrong | 15/15 both ok, 7 full wrong | 0/126 |
| qwen3-32b | none | 54/60 both ok, 11 full wrong | 37/39 both ok, 5 full wrong | 36/39 both ok, 1 full wrong | 14/15 both ok, 1 full wrong | 0/126 |
| qwen3-8b | calc | 41/60 both ok, 30 full wrong | 35/39 both ok, 19 full wrong | 29/39 both ok, 18 full wrong | 9/15 both ok, 5 full wrong | 0/126 |
| qwen3-8b | none | 32/60 both ok, 29 full wrong | 27/39 both ok, 12 full wrong | 24/39 both ok, 14 full wrong | 11/15 both ok, 7 full wrong | 0/126 |
