WITH customer_transaction_counts AS (
  SELECT
    c.customerid,
    COUNT(t.transactionid) as transaction_count
  FROM customers c
  LEFT JOIN transactions_1k t ON c.customerid = t.customerid
  GROUP BY c.customerid
  HAVING COUNT(t.transactionid) > 0
)
SELECT
  customerid,
  transaction_count
FROM customer_transaction_counts
WHERE transaction_count > 1;
