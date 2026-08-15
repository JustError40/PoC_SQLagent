SELECT segment, COUNT(*) as station_count FROM gasstations GROUP BY segment ORDER BY station_count DESC;
