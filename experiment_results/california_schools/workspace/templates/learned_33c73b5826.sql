SELECT sc.phone FROM satscores s JOIN schools sc ON s.cds = sc.cdscode WHERE sc.district = 'Fresno Unified' ORDER BY s.avgscrread ASC LIMIT 1;
