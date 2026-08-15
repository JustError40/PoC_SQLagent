SELECT date, COUNT(*) as transaction_count FROM transactions_1k GROUP BY date ORDER BY transaction_count DESC LIMIT 10;
