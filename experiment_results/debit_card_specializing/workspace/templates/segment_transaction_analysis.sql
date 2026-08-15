SELECT customers.segment, COUNT(*) AS txn_count FROM transactions_1k JOIN customers ON CAST(transactions_1k.customerid AS integer) = CAST(customers.customerid AS integer) GROUP BY customers.segment;
