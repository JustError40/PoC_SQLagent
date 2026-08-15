WITH customer_monthly AS (
  SELECT
    customerid,
    date,
    consumption
  FROM yearmonth
  WHERE customerid IS NOT NULL
)
SELECT
  customerid,
  COUNT(*) as month_count,
  SUM(consumption) as total_consumption,
  AVG(consumption) as avg_consumption
FROM customer_monthly
GROUP BY customerid
ORDER BY month_count DESC
LIMIT 50;
