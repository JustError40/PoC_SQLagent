SELECT customerid, COUNT(*) as transaction_count, MIN(date) as first_tx, MAX(date) as last_tx FROM transactions_1k GROUP BY customerid HAVING COUNT(*) > 1 ORDER BY transaction_count DESC LIMIT 100;
