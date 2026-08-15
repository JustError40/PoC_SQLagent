SELECT p.description, COUNT(*) as transaction_count FROM transactions_1k t JOIN products p ON t.productid = p.productid GROUP BY p.description ORDER BY transaction_count DESC LIMIT 20;
