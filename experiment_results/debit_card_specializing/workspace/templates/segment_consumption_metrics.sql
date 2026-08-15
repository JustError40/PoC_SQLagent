SELECT c.segment, COUNT(*) as consumption_records FROM customers c INNER JOIN yearmonth y ON c.customerid = y.customerid GROUP BY c.segment ORDER BY consumption_records DESC;
