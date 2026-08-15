SELECT
  sc.virtual,
  AVG(s.avgscrread) as avg_reading,
  AVG(s.avgscrmath) as avg_math,
  AVG(s.avgscrwrite) as avg_writing,
  COUNT(*) as record_count
FROM satscores s
JOIN schools sc ON s.cds = sc.cdscode
WHERE s.cds IS NOT NULL AND sc.cdscode IS NOT NULL
GROUP BY sc.virtual
ORDER BY record_count DESC;
