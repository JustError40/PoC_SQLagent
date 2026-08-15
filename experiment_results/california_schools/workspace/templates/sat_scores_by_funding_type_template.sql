WITH sat_school_join AS (
  SELECT
    satscores.cds,
    satscores.avgscrread,
    satscores.avgscrmath,
    satscores.avgscrwrite,
    schools.fundingtype,
    schools.virtual,
    schools.soctype
  FROM satscores
  JOIN schools ON satscores.cds = schools.cdscode
  WHERE satscores.avgscrread IS NOT NULL
    AND satscores.avgscrmath IS NOT NULL
    AND satscores.avgscrwrite IS NOT NULL
)
SELECT
  fundingtype,
  virtual,
  soctype,
  AVG(avgscrread) as avg_reading,
  AVG(avgscrmath) as avg_math,
  AVG(avgscrwrite) as avg_writing,
  COUNT(*) as school_count
FROM sat_school_join
GROUP BY fundingtype, virtual, soctype
ORDER BY avg_reading DESC;
