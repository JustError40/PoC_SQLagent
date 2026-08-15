SELECT
  rtype,
  COUNT(*) AS total_records,
  SUM(CASE WHEN avgscrread IS NULL THEN 1 ELSE 0 END) AS null_readings,
  SUM(CASE WHEN avgscrmath IS NULL THEN 1 ELSE 0 END) AS null_math,
  SUM(CASE WHEN avgscrwrite IS NULL THEN 1 ELSE 0 END) AS null_writing
FROM satscores
GROUP BY rtype
ORDER BY rtype;
