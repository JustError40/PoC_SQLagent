WITH product_stats AS (
  SELECT
    p.productid,
    p.description,
    COUNT(*) as transaction_count,
    SUM(t.amount) as total_value,
    COUNT(DISTINCT t.customerid) as unique_customers
  FROM transactions_1k t
  INNER JOIN products p ON t.productid = p.productid
  GROUP BY p.productid, p.description
)
SELECT
  productid,
  description,
  transaction_count,
  total_value,
  unique_customers,
  ROUND(total_value * 100.0 / SUM(total_value) OVER(), 2) as value_percentage
FROM product_stats
ORDER BY total_value DESC;
