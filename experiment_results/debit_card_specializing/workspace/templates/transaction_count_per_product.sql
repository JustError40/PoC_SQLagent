SELECT p.productid, COUNT(t.transactionid) as transaction_count FROM products p JOIN transactions_1k t ON p.productid = t.productid GROUP BY p.productid ORDER BY transaction_count DESC LIMIT 20;
