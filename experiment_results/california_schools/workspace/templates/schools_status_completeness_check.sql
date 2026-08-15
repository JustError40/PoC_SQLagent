SELECT statustype, count(*) as school_count, count(*) FILTER (WHERE statustype IS NOT NULL) as valid_count FROM schools GROUP BY statustype ORDER BY school_count DESC;
