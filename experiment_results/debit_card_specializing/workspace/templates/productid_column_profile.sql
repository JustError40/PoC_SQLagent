SELECT COUNT(DISTINCT productid) as unique_products, COUNT(*) as total_transactions, AVG(amount) as avg_amount FROM transactions_1k;
