SELECT
  COUNT(*) as total_transactions,
  AVG(amount) as avg_amount,
  AVG(price) as avg_price,
  MAX(amount) - MIN(amount) as amount_range,
  MAX(price) - MIN(price) as price_range,
  COUNT(DISTINCT amount) as unique_amounts,
  COUNT(DISTINCT price) as unique_prices
FROM transactions_1k;
