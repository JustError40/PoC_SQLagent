SELECT p.description FROM transactions_1k t JOIN gasstations g ON t.gasstationid = g.gasstationid JOIN products p ON t.productid = p.productid WHERE g.country = 'Czech Republic';
