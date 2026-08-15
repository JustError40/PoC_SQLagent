WITH virtual_schools AS (
  SELECT
    frpm.cdscode,
    frpm."Enrollment (K-12)",
    schools.charter,
    schools.virtual,
    schools.fundingtype
  FROM frpm
  JOIN schools ON frpm.cdscode = schools.cdscode
  WHERE schools.virtual = 'Y'
  AND frpm."FRPM Count (K-12)" > 0
)
SELECT
  COUNT(*) as virtual_school_count,
  AVG(virtual_schools."Enrollment (K-12)") as avg_virtual_enrollment,
  COUNT(DISTINCT virtual_schools.charter) as charter_count,
  COUNT(DISTINCT virtual_schools.fundingtype) as funding_type_count
FROM virtual_schools;
