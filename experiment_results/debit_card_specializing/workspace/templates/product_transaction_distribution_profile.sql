WITH product_amount_stats AS (
  SELECT
    productid,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount,
    MIN(amount) as min_amount,
    MAX(amount) as max_amount,
    COUNT(DISTINCT amount) as distinct_amounts,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) as median_amount,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY amount) as q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY amount) as q3
  FROM transactions_1k
  GROUP BY productid
)
SELECT * FROM product_amount_stats ORDER BY total_amount DESC LIMIT 50;
