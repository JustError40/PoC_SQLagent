# Evolution experiment — debit_card_specializing

- Corpus: evals/bird_debit_card_specializing.golden.jsonl (30 questions)
- Run ID (workspace): server-debit_card_specializing-20260815-092327
- Database: debit_card_specializing
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 3 | 12 | 5 | 1 | 3 | 6 | 0 | 0 | 19/0/0/1 | 10.7 |
| iteration 1 | 4 | 13 | 5 | 1 | 0 | 7 | 0 | 0 | 20/0/1/1 | 53.4 |
| iteration 2 | 3 | 14 | 5 | 1 | 1 | 6 | 0 | 0 | 20/0/1/1 | 23.2 |
| iteration 3 | 3 | 13 | 6 | 1 | 2 | 5 | 0 | 0 | 20/0/2/0 | 83.6 |
| iteration 4 | 4 | 11 | 7 | 1 | 4 | 3 | 0 | 0 | 20/0/2/0 | 23.8 |
| iteration 5 | 4 | 12 | 9 | 1 | 0 | 4 | 0 | 0 | 22/1/2/0 | 53.4 |
| iteration 6 | 6 | 9 | 7 | 1 | 3 | 4 | 0 | 0 | 18/1/2/1 | 19.5 |
| iteration 7 | 5 | 10 | 8 | 1 | 1 | 5 | 0 | 0 | 20/1/2/0 | 20.0 |
| iteration 8 | 6 | 10 | 8 | 1 | 2 | 3 | 0 | 0 | 20/3/1/0 | 61.0 |
| iteration 9 | 5 | 9 | 8 | 1 | 3 | 4 | 0 | 0 | 20/2/0/0 | 14.7 |
| iteration 10 | 5 | 10 | 11 | 1 | 0 | 3 | 0 | 0 | 24/1/0/1 | 15.4 |
