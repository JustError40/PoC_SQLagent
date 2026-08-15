WITH virtual_schools AS (
  SELECT
    f.cdscode,
    f."Charter Funding Type" as funding_type,
    f."Enrollment (K-12)" as enrollment_k12,
    s.virtual,
    s.fundingtype
  FROM frpm f
  JOIN schools s ON f.cdscode = s.cdscode
  WHERE s.virtual = 'Y'
)
SELECT
  funding_type,
  COUNT(*) as school_count,
  AVG(enrollment_k12) as avg_enrollment_k12,
  SUM(enrollment_k12) as total_enrollment_k12
FROM virtual_schools
GROUP BY funding_type
ORDER BY total_enrollment_k12 DESC;
