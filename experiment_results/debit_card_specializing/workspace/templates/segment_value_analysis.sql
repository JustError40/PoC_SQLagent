SELECT c.segment, SUM(t.amount) as total_transaction_value, COUNT(t.transactionid) as transaction_count
FROM transactions_1k t
JOIN customers c ON t.customerid = c.customerid
GROUP BY c.segment
ORDER BY total_transaction_value DESC;
