SELECT cardid, COUNT(*) as transaction_count FROM transactions_1k GROUP BY cardid ORDER BY transaction_count DESC LIMIT 50;
