SELECT s.mailstreet || ' ' || s.mailcity || ', ' || s.zip || ', ' || s.state AS postal_street_address, s.school AS school_name
FROM satscores sa
JOIN schools s ON sa.cds = s.soc
ORDER BY sa.avgscrmath DESC
LIMIT 1 OFFSET 6;
