WITH product_transaction_counts AS (
  SELECT
    t.productid,
    p.description,
    COUNT(*) as transaction_count,
    SUM(t.amount) as total_amount,
    AVG(t.amount) as avg_amount
  FROM transactions_1k t
  INNER JOIN products p ON t.productid = p.productid
  GROUP BY t.productid, p.description
)
SELECT
  description,
  transaction_count,
  total_amount,
  avg_amount
FROM product_transaction_counts
ORDER BY transaction_count DESC
LIMIT 50;
