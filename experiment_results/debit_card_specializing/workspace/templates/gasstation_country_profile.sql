SELECT country, COUNT(*) as station_count, COUNT(DISTINCT gasstationid) as unique_stations FROM gasstations GROUP BY country ORDER BY station_count DESC;
