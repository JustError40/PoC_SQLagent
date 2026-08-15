WITH amount_stats AS (
  SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) as median_amount,
    COUNT(DISTINCT amount) as distinct_amounts,
    AVG(amount) as avg_amount
  FROM transactions_1k
) SELECT * FROM amount_stats;
