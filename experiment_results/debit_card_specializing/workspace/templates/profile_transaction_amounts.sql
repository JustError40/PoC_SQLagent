SELECT
  MIN(amount) as min_amount,
  MAX(amount) as max_amount,
  ROUND(AVG(amount), 2) as avg_amount,
  COUNT(DISTINCT amount) as distinct_amounts,
  COUNT(*) as total_transactions
FROM transactions_1k
LIMIT 1;
