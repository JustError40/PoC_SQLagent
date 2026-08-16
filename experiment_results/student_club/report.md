# Evolution experiment — student_club

- Corpus: evals/bird_student_club.golden.jsonl (46 questions)
- Run ID (workspace): server-student_club-20260815-092327
- Database: student_club
- Control = run without learning stages (model noise baseline)
- Judge: hosted_vllm/gemma4-chat (reporting only; verdicts are never fed back to the agent)

| Run | Correct | Wrong answer | Compare error | Clarified | Fail: schema/JSON | Fail: react | Fail: LLM | Fail: other | Judge: correct/partial/incorrect/inconclusive | Time, min |
|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 11 | 21 | 8 | 0 | 3 | 3 | 0 | 0 | 33/0/4/3 | 18.3 |
| iteration 1 | 14 | 19 | 8 | 0 | 2 | 3 | 0 | 0 | 36/0/3/2 | 55.5 |
| iteration 2 | 13 | 16 | 11 | 0 | 2 | 4 | 0 | 0 | 35/0/3/2 | 27.2 |
| iteration 3 | 13 | 17 | 11 | 0 | 4 | 1 | 0 | 0 | 33/0/4/4 | 33.3 |
| iteration 4 | 13 | 12 | 11 | 0 | 3 | 7 | 0 | 0 | 31/0/2/3 | 22.4 |
| iteration 5 | 11 | 7 | 26 | 0 | 0 | 2 | 0 | 0 | 19/0/25/0 | 9.0 |
| iteration 6 | 10 | 14 | 12 | 0 | 5 | 5 | 0 | 0 | 30/0/1/5 | 37.6 |
| iteration 7 | 10 | 13 | 19 | 0 | 1 | 3 | 0 | 0 | 33/0/5/4 | 26.7 |
| iteration 8 | 10 | 17 | 18 | 0 | 0 | 1 | 0 | 0 | 34/1/5/5 | 49.1 |
