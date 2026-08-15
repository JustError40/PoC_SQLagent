SELECT
  c.segment,
  COUNT(t.transactionid) as transaction_count,
  SUM(t.amount) as total_spend,
  AVG(t.amount) as avg_spend
FROM customers c
JOIN transactions_1k t ON c.customerid = t.customerid
WHERE c.segment IS NOT NULL
GROUP BY c.segment
ORDER BY total_spend DESC;
