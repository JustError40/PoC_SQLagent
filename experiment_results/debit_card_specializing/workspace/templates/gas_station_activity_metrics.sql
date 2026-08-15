WITH gasstation_counts AS (
  SELECT
    gasstationid,
    COUNT(*) as transaction_count
  FROM transactions_1k
  GROUP BY gasstationid
)
SELECT
  gasstationid,
  transaction_count,
  CASE
    WHEN transaction_count < 5 THEN 'low'
    WHEN transaction_count < 20 THEN 'medium'
    ELSE 'high'
  END as activity_level
FROM gasstation_counts
ORDER BY transaction_count DESC
LIMIT 20;
