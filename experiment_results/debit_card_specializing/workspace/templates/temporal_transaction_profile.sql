SELECT date, COUNT(*) as transaction_count, COUNT(DISTINCT customerid) as unique_customers, COUNT(DISTINCT gasstationid) as unique_stations FROM transactions_1k GROUP BY date ORDER BY date LIMIT 50;
