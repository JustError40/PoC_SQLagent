WITH product_segment_stats AS (
  SELECT
    p.productid,
    c.segment,
    COUNT(*) as transaction_count,
    SUM(t.amount) as total_amount
  FROM transactions_1k t
  JOIN products p ON t.productid = p.productid
  JOIN customers c ON t.customerid = c.customerid
  GROUP BY p.productid, c.segment
)
SELECT
  segment,
  productid,
  transaction_count,
  total_amount
FROM product_segment_stats
ORDER BY transaction_count DESC;
