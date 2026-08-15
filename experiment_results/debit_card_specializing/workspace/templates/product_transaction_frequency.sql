SELECT productid, COUNT(*) as transaction_count, AVG(amount) as avg_amount FROM transactions_1k GROUP BY productid ORDER BY transaction_count DESC;
