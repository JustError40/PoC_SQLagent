SELECT g.country, COUNT(t.transactionid) as transaction_count
FROM transactions_1k t
JOIN gasstations g ON t.gasstationid = g.gasstationid
GROUP BY g.country
ORDER BY transaction_count DESC;
