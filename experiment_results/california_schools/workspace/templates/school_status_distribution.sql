SELECT
  statustype,
  COUNT(*) as school_count,
  COUNT(*) FILTER (WHERE opendate IS NOT NULL) as open_count,
  COUNT(*) FILTER (WHERE closeddate IS NOT NULL) as closed_count
FROM schools
GROUP BY statustype
ORDER BY school_count DESC;
