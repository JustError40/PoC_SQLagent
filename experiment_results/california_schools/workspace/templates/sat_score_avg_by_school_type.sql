SELECT COUNT(*) FILTER (WHERE s.rtype IS NOT NULL) as total_records,
       COUNT(*) FILTER (WHERE s.rtype IS NOT NULL AND s.cds = sc.virtual) as virtual_records,
       AVG(s.avgscrread) FILTER (WHERE s.rtype IS NOT NULL) as avg_read,
       AVG(s.avgscrmath) FILTER (WHERE s.rtype IS NOT NULL) as avg_math,
       AVG(s.avgscrwrite) FILTER (WHERE s.rtype IS NOT NULL) as avg_write
FROM satscores s
JOIN schools sc ON s.cds = sc.cdscode
WHERE sc.virtual IS NOT NULL
GROUP BY sc.virtual;
