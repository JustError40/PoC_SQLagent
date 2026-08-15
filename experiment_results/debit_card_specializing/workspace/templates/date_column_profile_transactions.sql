SELECT date, COUNT(*) as transaction_count FROM transactions_1k GROUP BY date ORDER BY date DESC LIMIT 50;
