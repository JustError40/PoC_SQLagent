WITH customer_monthly AS (
  SELECT
    c.customerid,
    ym.date,
    SUM(ym.consumption) as total_consumption,
    AVG(ym.consumption) as avg_consumption,
    COUNT(ym.date) as transaction_count
  FROM customers c
  INNER JOIN yearmonth ym ON c.customerid = ym.customerid
  GROUP BY c.customerid, ym.date
)
SELECT
  customerid,
  date as month,
  total_consumption,
  avg_consumption,
  transaction_count
FROM customer_monthly
ORDER BY customerid, date
LIMIT 50;
