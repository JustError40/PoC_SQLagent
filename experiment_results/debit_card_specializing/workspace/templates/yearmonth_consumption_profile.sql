SELECT consumption, COUNT(*) as customer_count, ROUND(AVG(consumption)::numeric, 2) as avg_consumption FROM yearmonth GROUP BY consumption ORDER BY avg_consumption DESC LIMIT 100;
