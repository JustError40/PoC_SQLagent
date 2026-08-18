# Multi-DB self-evolution campaign — aggregated results

- Campaign: smoke3-20260817-085834 (branch `campaign/smoke3-20260817-085834`)
- Golden answers were used for scoring ONLY; the agent learned exclusively from its own failures via the standard learning stages.
- control = corpus run without learning stages (noise baseline).

## california_schools (30 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 1 | 17 | 7 | 0 | 5 | 6% |
| iteration 1 | 2 | 17 | 8 | 0 | 3 | 11% |
| iteration 2 | 2 | 17 | 8 | 0 | 3 | 11% |
| iteration 3 | 1 | 8 | 2 | 0 | 19 | 11% |
| iteration 4 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 30 | - |

Baseline vs final: correct 1 → 0 (-1).

## debit_card_specializing (30 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 30 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 30 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 30 | - |

Baseline vs final: correct 0 → 0 (+0).

## student_club (46 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 46 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 46 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 46 | - |

Baseline vs final: correct 0 → 0 (+0).

## superhero (52 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 52 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 52 | - |

Baseline vs final: correct 0 → 0 (+0).

## toxicology (40 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 40 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 40 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 40 | - |

Baseline vs final: correct 0 → 0 (+0).

## thrombosis_prediction (50 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 50 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 50 | - |

Baseline vs final: correct 0 → 0 (+0).

## formula_1 (66 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 66 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 66 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 66 | - |

Baseline vs final: correct 0 → 0 (+0).

## financial (32 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 32 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 32 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 32 | - |

Baseline vs final: correct 0 → 0 (+0).

## card_games (52 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 52 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 52 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 52 | - |

Baseline vs final: correct 0 → 0 (+0).

## european_football_2 (50 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 50 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 50 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 50 | - |

Baseline vs final: correct 0 → 0 (+0).

## codebase_community (48 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 0 | 0 | 0 | 0 | 48 | - |
| iteration 1 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 2 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 3 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 4 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 5 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 6 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 7 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 8 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 9 | 0 | 0 | 0 | 0 | 48 | - |
| iteration 10 | 0 | 0 | 0 | 0 | 48 | - |

Baseline vs final: correct 0 → 0 (+0).
