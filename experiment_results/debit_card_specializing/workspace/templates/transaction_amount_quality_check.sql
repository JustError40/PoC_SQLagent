SELECT
  SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END) as null_amounts,
  SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END) as zero_amounts,
  COUNT(*) as total_rows,
  SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as positive_amounts
FROM transactions_1k;
