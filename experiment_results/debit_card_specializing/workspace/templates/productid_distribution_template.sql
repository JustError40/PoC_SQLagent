SELECT productid, COUNT(*) as purchase_count, COUNT(DISTINCT customerid) as unique_customers FROM transactions_1k GROUP BY productid ORDER BY purchase_count DESC LIMIT 20;
