SELECT
  s.charter,
  COUNT(*) as school_count,
  AVG(f."Enrollment (K-12)") as avg_k12_enrollment,
  SUM(f."Enrollment (K-12)") as total_k12_enrollment
FROM frpm f
JOIN schools s ON f.cdscode = s.cdscode
WHERE f.cdscode IS NOT NULL AND s.cdscode IS NOT NULL
GROUP BY s.charter
ORDER BY school_count DESC;
