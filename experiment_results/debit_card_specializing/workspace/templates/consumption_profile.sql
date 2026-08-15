SELECT consumption, COUNT(*) as customer_count FROM yearmonth GROUP BY consumption ORDER BY consumption DESC LIMIT 20;
