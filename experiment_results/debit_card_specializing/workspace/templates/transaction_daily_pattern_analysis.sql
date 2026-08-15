SELECT date_trunc('day', date) as day, COUNT(*) as transaction_count FROM transactions_1k GROUP BY day ORDER BY day DESC LIMIT 100;
