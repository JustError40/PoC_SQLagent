# Evolution experiment — debit_card_specializing

- Corpus: evals/bird_debit_card_specializing.golden.jsonl (30 questions)
- Run ID (workspace): server-debit_card_specializing-20260815-092123
- Database: debit_card_specializing
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 4 | 10 | 9 | 1 | 3 | 3 | 0 | 0 | 19/1/2/1 | 16.0 |
| iteration 1 | 3 | 12 | 7 | 1 | 0 | 6 | 0 | 1 | 18/0/3/1 | 59.4 |
| iteration 2 | 4 | 11 | 10 | 1 | 1 | 3 | 0 | 0 | 22/1/2/0 | 20.9 |
