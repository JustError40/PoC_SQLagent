# Multi-DB self-evolution campaign — aggregated results

- Campaign: smoke-20260817-074714 (branch `campaign/smoke-20260817-074714`)
- Golden answers were used for scoring ONLY; the agent learned exclusively from its own failures via the standard learning stages.
- control = corpus run without learning stages (noise baseline).

## california_schools (30 questions)

| Run | Correct | Incorrect | Empty | Clarified | Pipeline failed | Verified |
|---|---|---|---|---|---|---|
| control | 1 | 7 | 3 | 0 | 19 | 12% |

Baseline vs final: correct 1 → 1 (+0).
