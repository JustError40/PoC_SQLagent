SELECT DISTINCT schools.admemail1, schools.admemail2, schools.admemail3
FROM schools
WHERE schools.city = 'San Bernardino'
  AND schools.county = 'San Bernardino'
  AND schools.district = 'City of San Bernardino City Unified'
  AND schools.opendate BETWEEN '2009-01-01' AND '2010-12-31'
  AND schools.soc IN ('INTMIDJR', 'U');
