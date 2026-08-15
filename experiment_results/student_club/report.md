# Evolution experiment — student_club

- Corpus: evals/bird_student_club.golden.jsonl (46 questions)
- Run ID (workspace): server-student_club-20260815-092327
- Database: student_club
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 11 | 21 | 8 | 0 | 3 | 3 | 0 | 0 | 33/0/4/3 | 18.3 |
