SELECT DISTINCT p.description FROM products p JOIN transactions_1k t ON p.productid = t.productid WHERE t.date >= '2013-09-01' AND t.date < '2013-10-01';
