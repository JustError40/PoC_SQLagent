WITH segment_transactions AS (
  SELECT
    c.segment,
    COUNT(DISTINCT t.transactionid) as transaction_count,
    SUM(t.amount) as total_value,
    AVG(t.amount) as avg_transaction_value
  FROM transactions_1k t
  JOIN customers c ON t.customerid = c.customerid
  GROUP BY c.segment
)
SELECT * FROM segment_transactions ORDER BY total_value DESC;
