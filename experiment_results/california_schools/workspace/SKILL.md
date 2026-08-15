# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Explicitly link column references to their source tables in non-aggregate clauses.
- Validate column scope visibility immediately after defining JOINs before referencing in WHERE or SELECT.
- Prioritize explicit JOIN keywords over comma-separated table lists to ensure clear join intent.
- Structure multi-step logic using Common Table Expressions (CTEs) to isolate filtering from aggregation.
- Explicitly enumerate selected columns in the SELECT clause to avoid implicit wildcard selection.
- Enforce PostgreSQL-specific placeholders (%s, %b, %t) in all dynamic string formatting to prevent syntax errors.
- Prioritize static parameterized queries over dynamic string concatenation to reduce structural syntax risks.
- Implement pre-execution validation for function arguments to catch placeholder mismatches before runtime.
