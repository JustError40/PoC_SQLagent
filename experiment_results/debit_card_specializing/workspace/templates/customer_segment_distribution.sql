SELECT segment, COUNT(*) as segment_count, COUNT(DISTINCT customerid) as unique_customers FROM customers GROUP BY segment ORDER BY segment_count DESC;
