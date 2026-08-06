WITH monthly_rev AS (
  SELECT date_trunc('month', event_date) AS month,
         SUM(revenue) AS total_rev
  FROM store_returns
  GROUP BY month
)
SELECT 'store_returns' AS table_name,
        'one row per month' AS grain,
        'no issue' AS issue
FROM monthly_rev;
