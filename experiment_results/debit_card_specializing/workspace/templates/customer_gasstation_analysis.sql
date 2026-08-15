WITH customer_station_activity AS (
  SELECT
    c.segment,
    c.currency,
    g.chainid,
    g.country,
    COUNT(*) as total_transactions,
    SUM(t.amount) as total_spent,
    AVG(t.amount) as avg_transaction_amount
  FROM transactions_1k t
  INNER JOIN customers c ON t.customerid = c.customerid
  INNER JOIN gasstations g ON t.gasstationid = g.gasstationid
  GROUP BY c.segment, c.currency, g.chainid, g.country
)
SELECT
  segment,
  chainid,
  country,
  total_transactions,
  total_spent,
  avg_transaction_amount
FROM customer_station_activity
ORDER BY total_spent DESC
LIMIT 100;
