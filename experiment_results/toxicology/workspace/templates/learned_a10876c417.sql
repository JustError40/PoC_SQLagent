SELECT AVG(s.numtsttakr) AS avg_test_takers FROM satscores s JOIN schools sch ON s.cds = sch.cdscode WHERE sch.county = 'Fresno' AND sch.opendate >= '1980-01-01' AND sch.opendate <= '1980-12-31';
