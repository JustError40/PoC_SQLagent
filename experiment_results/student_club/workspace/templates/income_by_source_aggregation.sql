SELECT source, COUNT(*) as transaction_count, SUM(amount) as total_amount, AVG(amount) as avg_amount FROM income GROUP BY source ORDER BY total_amount DESC;
