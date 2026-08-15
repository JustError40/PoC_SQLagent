WITH amount_stats AS (
  SELECT
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY amount) AS p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY amount) AS p50,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY amount) AS p75,
    COUNT(*) FILTER (WHERE amount IS NOT NULL) AS total_count,
    COUNT(*) FILTER (WHERE amount < 0) AS negative_count,
    COUNT(*) FILTER (WHERE amount = 0) AS zero_count
  FROM transactions_1k
)
SELECT * FROM amount_stats;
