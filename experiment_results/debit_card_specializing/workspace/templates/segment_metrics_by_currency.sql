SELECT c.segment, c.currency, COUNT(*) as transaction_count FROM transactions_1k t JOIN customers c ON t.customerid = c.customerid GROUP BY c.segment, c.currency ORDER BY transaction_count DESC;
