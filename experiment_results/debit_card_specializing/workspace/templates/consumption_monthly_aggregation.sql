SELECT customerid, date, AVG(consumption) as avg_consumption, SUM(consumption) as total_consumption FROM yearmonth GROUP BY customerid, date ORDER BY customerid, date LIMIT 100;
