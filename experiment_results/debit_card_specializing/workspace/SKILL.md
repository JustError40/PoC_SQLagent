# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Ensure join keys are primary or unique constraints rather than relying solely on indexes.
- Ensure `ORDER BY` columns are indexed to guarantee efficient sorting performance.
- Avoid `SELECT *` to minimize network overhead and improve cache locality.
- Cap join result sets with `LIMIT` to prevent unbounded cartesian expansion.
- Verify index coverage on `WHERE` predicates independently of `ORDER BY` column indexing.
- Query Shapes: Enforce explicit casts to prevent implicit type conversions that alter execution plans.
- Join Discipline: Filter on high-cardinality columns before joining to minimize intermediate row counts.
- Identifier Habits: Enforce explicit table aliases to ensure unambiguous column references in complex joins.
