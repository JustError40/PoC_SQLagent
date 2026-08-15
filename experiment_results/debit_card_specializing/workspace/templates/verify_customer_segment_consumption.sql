SELECT c.segment, COUNT(*) as consumption_count FROM customers c LEFT JOIN yearmonth y ON c.customerid = y.customerid GROUP BY c.segment ORDER BY consumption_count DESC;
