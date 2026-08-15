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
| iteration 4 | 2 | 11 | 5 | 0 | 0 | 12 | 0 | 0 | 13/1/3/1 | 22.5 |
| iteration 5 | 3 | 10 | 5 | 0 | 2 | 10 | 0 | 0 | 15/1/1/1 | 27.2 |
| iteration 6 | 2 | 12 | 5 | 0 | 0 | 11 | 0 | 0 | 15/1/2/1 | 23.6 |
| iteration 7 | 2 | 11 | 6 | 0 | 0 | 11 | 0 | 0 | 16/0/1/2 | 16.5 |
| iteration 8 | 2 | 13 | 5 | 0 | 0 | 10 | 0 | 0 | 15/1/2/2 | 57.1 |
| iteration 9 | 2 | 11 | 6 | 0 | 0 | 9 | 0 | 2 | 14/1/3/1 | 31.0 |
