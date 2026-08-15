SELECT segment, COUNT(*) as segment_count FROM customers GROUP BY segment ORDER BY segment_count DESC;
