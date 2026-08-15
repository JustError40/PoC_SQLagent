# Evolution experiment — california_schools

- Corpus: evals/bird_california_schools.golden.jsonl (30 questions)
- Run ID (workspace): server-california_schools-20260815-084602
- Database: california_schools
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 3 | 6 | 7 | 0 | 3 | 9 | 0 | 2 | 0/0/0/16 | 14.2 |
