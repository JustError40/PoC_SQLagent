# Evolution experiment — california_schools

- Corpus: evals/bird_california_schools.golden.jsonl (30 questions)
- Run ID (workspace): server-california_schools-20260815-092327
- Database: california_schools
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 2 | 11 | 4 | 0 | 3 | 10 | 0 | 0 | 15/1/0/1 | 23.4 |
| iteration 1 | 2 | 12 | 5 | 0 | 2 | 9 | 0 | 0 | 15/0/3/1 | 22.5 |
| iteration 2 | 2 | 11 | 5 | 0 | 1 | 11 | 0 | 0 | 14/1/2/1 | 24.4 |
| iteration 3 | 2 | 11 | 5 | 0 | 1 | 11 | 0 | 0 | 14/1/2/1 | 18.9 |
