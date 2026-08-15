SELECT COUNT(*) as total_schools, SUM(CASE WHEN virtual = 'Y' THEN 1 ELSE 0 END) as virtual_count, SUM(CASE WHEN virtual IS NULL THEN 1 ELSE 0 END) as null_virtual FROM schools LIMIT 10;
