WITH monthly_consumption AS (
  SELECT
    customerid,
    date,
    consumption,
    LAG(consumption) OVER (PARTITION BY customerid ORDER BY date) as prev_month_consumption,
    LEAD(consumption) OVER (PARTITION BY customerid ORDER BY date) as next_month_consumption
  FROM yearmonth
)
SELECT
  customerid,
  date,
  consumption,
  prev_month_consumption,
  next_month_consumption,
  ROUND(
    CASE WHEN prev_month_consumption > 0 THEN ((consumption - prev_month_consumption)::numeric) / (prev_month_consumption::numeric) * 100 ELSE 0 END,
    2
  ) as month_over_month_change_pct
FROM monthly_consumption
WHERE date >= '2025-01-01'
ORDER BY customerid, date
LIMIT 500;
