SELECT DISTINCT t.amount, t.price, t.customerid, c.segment, c.currency FROM transactions_1k t JOIN customers c ON t.customerid = c.customerid WHERE t.amount IS NOT NULL LIMIT 500;
