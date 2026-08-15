SELECT t.cardid, c.segment, COUNT(*) as usage_count FROM transactions_1k t JOIN customers c ON t.customerid = c.customerid GROUP BY t.cardid, c.segment ORDER BY usage_count DESC;
