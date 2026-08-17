SELECT AVG(s.numtsttakr)
FROM satscores s
JOIN schools sh ON s.cds = sh.cdscode
WHERE sh.city = 'Fresno'
  AND sh.opendate >= '1980-01-01'
  AND sh.opendate <= '1980-12-31';
