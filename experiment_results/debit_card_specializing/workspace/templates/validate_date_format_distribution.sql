SELECT date, COUNT(*) as transaction_count, COUNT(DISTINCT customerid) as unique_customers FROM transactions_1k WHERE date IS NOT NULL GROUP BY date ORDER BY date DESC LIMIT 50;
