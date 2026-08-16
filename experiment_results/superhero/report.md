# Evolution experiment — superhero

- Corpus: evals/bird_superhero.golden.jsonl (52 questions)
- Run ID (workspace): server-superhero-20260815-092327
- Database: superhero
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 8 | 22 | 13 | 0 | 9 | 0 | 0 | 0 | 37/1/3/2 | 21.4 |
