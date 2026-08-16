# Evolution experiment — student_club

- Corpus: evals/bird_student_club.golden.jsonl (46 questions)
- Run ID (workspace): server-student_club-20260815-092123
- Database: student_club
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 9 | 17 | 10 | 0 | 4 | 6 | 0 | 0 | 29/1/2/4 | 21.9 |
| iteration 1 | 10 | 15 | 15 | 0 | 0 | 6 | 0 | 0 | 32/0/3/5 | 63.5 |
| iteration 2 | 10 | 16 | 17 | 0 | 1 | 2 | 0 | 0 | 32/1/5/5 | 54.7 |
| iteration 3 | 9 | 16 | 19 | 0 | 0 | 2 | 0 | 0 | 36/1/5/2 | 73.6 |
| iteration 4 | 0 | 0 | 5 | 0 | 11 | 30 | 0 | 0 | 3/0/0/2 | 36.2 |
| iteration 5 | 0 | 0 | 4 | 0 | 5 | 37 | 0 | 0 | 3/0/0/1 | 24.4 |
