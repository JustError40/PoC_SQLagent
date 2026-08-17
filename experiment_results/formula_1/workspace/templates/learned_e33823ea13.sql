SELECT s.phone FROM satscores sc JOIN schools s ON sc.cds = s.cdscode WHERE sc.dname = 'Fresno Unified' ORDER BY sc.avgscrread ASC LIMIT 1;
