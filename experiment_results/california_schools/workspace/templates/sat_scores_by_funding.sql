SELECT
  satscores.rtype,
  schools.fundingtype,
  schools.virtual,
  COUNT(*) as record_count,
  AVG(satscores.avgscrmath) as avg_math
FROM satscores
JOIN schools ON satscores.cds = schools.cdscode
GROUP BY satscores.rtype, schools.fundingtype, schools.virtual;
