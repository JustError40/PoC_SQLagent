WITH enrollment_enrollments AS (
  SELECT
    f.cdscode,
    f."Enrollment (K-12)",
    f."FRPM Count (K-12)",
    s."avgscrread",
    s."avgscrmath",
    s."avgscrwrite",
    s."enroll12"
  FROM frpm f
  JOIN schools sc ON f.cdscode = sc.cdscode
  JOIN satscores s ON s.cds = sc.cdscode
  WHERE f."Enrollment (K-12)" IS NOT NULL
    AND f."FRPM Count (K-12)" IS NOT NULL
    AND s."avgscrread" IS NOT NULL
    AND s."avgscrmath" IS NOT NULL
    AND s."avgscrwrite" IS NOT NULL
    AND s."enroll12" IS NOT NULL
)
SELECT
  AVG("Enrollment (K-12)") as avg_enrollment,
  AVG("FRPM Count (K-12)") as avg_frpm_count,
  AVG("avgscrread") as avg_read_score,
  AVG("avgscrmath") as avg_math_score,
  AVG("avgscrwrite") as avg_write_score,
  AVG("enroll12") as avg_sat_enroll
FROM enrollment_enrollments;
