SELECT
    AVG(avgscrread) as avg_read_score,
    AVG(avgscrmath) as avg_math_score,
    AVG(avgscrwrite) as avg_write_score,
    COUNT(*) as total_schools,
    COUNT(DISTINCT rtype) as record_types,
    COUNT(DISTINCT sname) as unique_school_names
FROM satscores
LIMIT 100;
