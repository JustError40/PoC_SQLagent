# tpcds_sf10 skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Use explicit JOIN … ON without UNION ALL or implicit concatenation; embed subqueries via EXISTS when checking presence.
- Project only the selected key and necessary aggregates; avoid SELECT * in single‑row result.
- Never reuse temporary alias names across multiple queries within the same session.
- If join condition requires mixed types, create a separate derived view with matching types before joining to original tables.
- When aggregating over partitions, include all partition columns in GROUP BY and use MIN() for deterministic ordering.
- Prefix primary keys with 'id_' and versioned columns with '_vX' to keep identifiers unique across sessions.
- Materialize large hash-join resultsets in a temporary table before subsequent joins to guide the planner.
- Replace UPDATE ... SET column = expression with INSERT INTO target SELECT * FROM source WHERE condition for row-level updates.
