WITH null_stats AS (
  SELECT 'avgscrread' as column_name,
         COUNT(*) as total_rows,
         COUNT(avgscrread) as non_null_count,
         COUNT(*) FILTER (WHERE avgscrread IS NULL) as null_count,
         ROUND(COUNT(*) FILTER (WHERE avgscrread IS NULL)::numeric / COUNT(*) * 100, 2) as null_percentage
  FROM satscores
  UNION ALL
  SELECT 'avgscrmath' as column_name,
         COUNT(*) as total_rows,
         COUNT(avgscrmath) as non_null_count,
         COUNT(*) FILTER (WHERE avgscrmath IS NULL) as null_count,
         ROUND(COUNT(*) FILTER (WHERE avgscrmath IS NULL)::numeric / COUNT(*) * 100, 2) as null_percentage
  FROM satscores
  UNION ALL
  SELECT 'avgscrwrite' as column_name,
         COUNT(*) as total_rows,
         COUNT(avgscrwrite) as non_null_count,
         COUNT(*) FILTER (WHERE avgscrwrite IS NULL) as null_count,
         ROUND(COUNT(*) FILTER (WHERE avgscrwrite IS NULL)::numeric / COUNT(*) * 100, 2) as null_percentage
  FROM satscores
)
SELECT column_name, total_rows, non_null_count, null_count, null_percentage
FROM null_stats
ORDER BY column_name;
