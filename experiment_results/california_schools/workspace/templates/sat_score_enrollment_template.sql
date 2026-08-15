WITH score_enrollment AS (
  SELECT
    s.cdscode,
    s.soctype,
    s.virtual,
    s.fundingtype,
    COUNT(sc.cds) AS record_count,
    AVG(sc.avgscrread) AS avg_reading,
    AVG(sc.avgscrmath) AS avg_math,
    AVG(sc.avgscrwrite) AS avg_writing
  FROM schools s
  INNER JOIN satscores sc ON s.cdscode = sc.cds
  WHERE sc.rtype IS NOT NULL
  GROUP BY s.cdscode, s.soctype, s.virtual, s.fundingtype
)
SELECT
  soctype,
  virtual,
  fundingtype,
  record_count,
  ROUND(avg_reading, 2) AS avg_reading,
  ROUND(avg_math, 2) AS avg_math,
  ROUND(avg_writing, 2) AS avg_writing
FROM score_enrollment
ORDER BY record_count DESC;
