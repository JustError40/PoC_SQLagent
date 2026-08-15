SELECT COUNT(*) as total, ROUND(AVG(amount), 2) as avg_amount, ROUND(MIN(amount), 2) as min_amount, ROUND(MAX(amount), 2) as max_amount FROM transactions_1k WHERE amount IS NOT NULL;
