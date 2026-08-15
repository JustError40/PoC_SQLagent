SELECT country, COUNT(*) as station_count FROM gasstations GROUP BY country ORDER BY station_count DESC LIMIT 10;
