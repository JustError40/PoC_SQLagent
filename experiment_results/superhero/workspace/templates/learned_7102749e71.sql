SELECT s.admfname1, s.admlname1, s.admfname2, s.admlname2 FROM satscores sat JOIN schools s ON sat.cds = s.cdscode WHERE s.admfname1 IS NOT NULL ORDER BY sat.numge1500 DESC LIMIT 1;
