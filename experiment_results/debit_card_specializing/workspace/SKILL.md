# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Qualify all columns in `ORDER BY` and `GROUP BY` clauses with their table alias to prevent ambiguity and sorting errors.
- Use `INNER JOIN` by default and add `LEFT JOIN` only when null values from the left side are required.
- Apply SARGable predicates to WHERE clauses to maintain index efficiency without function wrapping.
- Utilize Common Table Expressions (CTEs) to modularize complex logic and improve query plan readability.
- Prefer EXISTS over IN for existence checks to reduce memory consumption and improve join performance.
- Order joins by descending table cardinality to minimize intermediate result size.
- Enforce explicit column aliases in all SELECT clauses to prevent ambiguity.
- Apply aggregation filters using HAVING instead of WHERE.
