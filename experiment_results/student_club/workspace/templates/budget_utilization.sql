WITH budget_utilization AS (
  SELECT
    e.event_id,
    b.budget_id,
    b.amount,
    b.spent,
    (CAST(b.spent AS NUMERIC) / NULLIF(b.amount, 0)) * 100 as utilization_pct
  FROM budget b
  JOIN event e ON b.link_to_event = e.event_id
  WHERE b.event_status = 'active'
)
SELECT * FROM budget_utilization ORDER BY utilization_pct DESC;
