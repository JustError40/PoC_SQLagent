SELECT g.country, COUNT(*) as transaction_count FROM transactions_1k t INNER JOIN gasstations g ON t.gasstationid = g.gasstationid GROUP BY g.country ORDER BY transaction_count DESC;
