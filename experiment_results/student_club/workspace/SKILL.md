# skill skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template from `manifest.yaml`. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
- No one-to-many fanout joins detected during survey.

## Lessons from exploration
- Use explicit schema prefixes for all table references to avoid cross-namespace collisions.
- Cap exploratory queries with LIMIT clauses to ensure safe resource usage.
- Validate column names against the specific table schema before referencing them.
- Ensure join conditions reference columns guaranteed to exist in both participating tables.
- Structure queries to select from the primary table first to establish context for subsequent joins.
- Ensure indexed columns are used in WHERE clauses for efficient lookups.
- Apply explicit aliases in SELECT clauses to distinguish data from multiple sources.
- Avoid SELECT * to prevent unnecessary data transfer and potential type conflicts.
