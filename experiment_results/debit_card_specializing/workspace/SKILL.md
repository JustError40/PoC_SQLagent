# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Explicitly define join intent (INNER vs LEFT) to ensure data integrity across multiple tables.
- Avoid correlated subqueries in WHERE clauses in favor of explicit JOINs for predictable execution plans.
- Fully qualify all table and column names with schema prefixes to eliminate ambiguity in multi-schema environments.
- Ensure join columns are indexed to guarantee efficient execution plans on large datasets.
- Use keyset pagination with a WHERE clause instead of OFFSET for large result sets to maintain consistent query plans.
- Explicitly enumerate columns in SELECT clauses to minimize I/O and avoid loading unnecessary metadata.
- Ensure all WHERE conditions on indexed columns are SARGABLE to preserve index usage efficiency.
- Use ONLY table selection in inheritance hierarchies to prevent unintended parent table data inclusion.
