SELECT rtype,
       COUNT(*) as record_count,
       SUM(CASE WHEN avgscrread IS NULL THEN 1 ELSE 0 END) as null_read,
       SUM(CASE WHEN avgscrmath IS NULL THEN 1 ELSE 0 END) as null_math,
       SUM(CASE WHEN avgscrwrite IS NULL THEN 1 ELSE 0 END) as null_write
FROM satscores
GROUP BY rtype;
