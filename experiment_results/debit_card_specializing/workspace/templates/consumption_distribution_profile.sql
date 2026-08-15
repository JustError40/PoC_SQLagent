SELECT consumption, COUNT(*) as consumption_count, MIN(consumption) as min_consumption, MAX(consumption) as max_consumption FROM yearmonth GROUP BY consumption ORDER BY consumption;
