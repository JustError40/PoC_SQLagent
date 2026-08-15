WITH product_transaction_counts AS (
  SELECT
    p.productid,
    p.description,
    COUNT(t.transactionid) as transaction_count,
    SUM(t.amount) as total_amount
  FROM products p
  JOIN transactions_1k t ON p.productid = t.productid
  GROUP BY p.productid, p.description
)
SELECT
  productid,
  description,
  transaction_count,
  total_amount
FROM product_transaction_counts
ORDER BY transaction_count DESC
LIMIT 15;
