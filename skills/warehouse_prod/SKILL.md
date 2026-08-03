# warehouse_prod skill

## Router
Use `manifest.yaml` first, then load only the domain and artifact files selected for the question.

## Query protocol
1. Identify the metric grain. 2. Prefer a template. 3. Keep queries read-only.
4. Run EXPLAIN before execution. 5. Check invariants before returning results.

## Grain rules
`orders.total_amount` is order grain. `order_items` and `order_payments` are one-to-many
relations and must not be joined when aggregating order-level measures unless pre-aggregated.
