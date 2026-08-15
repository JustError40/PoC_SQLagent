SELECT c.segment, t.date, COUNT(*) as transaction_count FROM transactions_1k t JOIN customers c ON t.customerid = c.customerid GROUP BY c.segment, t.date ORDER BY c.segment, t.date LIMIT 100;
