SELECT source, SUM(amount) as total_income, COUNT(*) as transaction_count FROM income GROUP BY source ORDER BY total_income DESC;
