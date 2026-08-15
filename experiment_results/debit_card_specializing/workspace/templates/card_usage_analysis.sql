SELECT cardid, COUNT(*) as transaction_count, COUNT(DISTINCT customerid) as unique_customers FROM transactions_1k GROUP BY cardid ORDER BY transaction_count DESC LIMIT 20;
