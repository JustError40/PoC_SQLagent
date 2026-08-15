WITH column_checks AS (
  SELECT 'avgscrread' as column_name, avgscrread as value FROM satscores
  UNION ALL
  SELECT 'avgscrmath' as column_name, avgscrmath as value FROM satscores
  UNION ALL
  SELECT 'avgscrwrite' as column_name, avgscrwrite as value FROM satscores
  UNION ALL
  SELECT 'enroll12' as column_name, enroll12 as value FROM satscores
  UNION ALL
  SELECT 'numtsttakr' as column_name, numtsttakr as value FROM satscores
)
SELECT
  column_name,
  COUNT(*) as total_records,
  SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) as null_count,
  ROUND(CAST(SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) AS DECIMAL(10,2))/CAST(COUNT(*) AS DECIMAL(10,2)) * 100, 2) as null_percentage
FROM column_checks
GROUP BY column_name
ORDER BY null_percentage DESC;
