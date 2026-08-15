SELECT c.segment, ym.date, SUM(ym.consumption) as total_consumption FROM yearmonth ym JOIN customers c ON ym.customerid = c.customerid GROUP BY c.segment, ym.date;
