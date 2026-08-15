SELECT
    s.school,
    AVG(sc.avgscrwrite) as avg_score,
    s.phone as communication_number
FROM satscores sc
JOIN schools s ON sc.cds = s.cdscode
WHERE s.opendate > '1991-01-01' OR s.closeddate < '2000-01-01'
GROUP BY s.school, s.phone
ORDER BY avg_score DESC;
