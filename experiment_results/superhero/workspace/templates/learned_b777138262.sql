SELECT s.school, s.fundingtype
FROM schools s
JOIN satscores sa ON s.cdscode = sa.cds
WHERE s.city = 'Riverside'
GROUP BY s.school, s.fundingtype
HAVING AVG(sa.avgscrmath) > 400;
