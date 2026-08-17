# Multi-DB self-evolution campaign — aggregated results

- Campaign: smoke3-20260817-085834 (branch `campaign/smoke3-20260817-085834`)
- Golden answers were used for scoring ONLY; the agent learned exclusively from its own failures via the standard learning stages.
- control = corpus run without learning stages (noise baseline).

## california_schools (30 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 3 | 15 | 6 | 0 | 6 | 17% |

Baseline vs final: correct 3 → 3 (+0).
