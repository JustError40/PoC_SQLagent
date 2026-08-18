SELECT s.phone FROM schools s JOIN satscores sa ON s.cdscode = sa.cds WHERE sa.dname = 'Fresno Unified' ORDER BY sa.avgscrread ASC LIMIT 1;
