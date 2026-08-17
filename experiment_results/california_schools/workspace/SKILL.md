# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Explicitly declare join types and use ON clauses instead of implicit joins.
- Select only required columns to minimize network overhead and index usage.
- Always run EXPLAIN (ANALYZE) on non-trivial queries to validate index strategy before execution.
- Prefer Common Table Expressions (CTEs) over nested subqueries for improved readability and debugging.
- Enforce a maximum row limit on all SELECT statements to prevent unbounded memory consumption.
- Validate clause termination for ORDER BY and GROUP BY to prevent truncation errors.
- Ensure column aliases are fully defined and unique to avoid parsing ambiguity.
- Verify CTE column names match SELECT lists to resolve structural parse failures.
