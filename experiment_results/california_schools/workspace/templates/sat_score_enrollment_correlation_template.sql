SELECT AVG(sats.enroll12) as avg_enrollment,
     AVG(sats.avgscrread) as avg_read_score,
     AVG(sats.avgscrmath) as avg_math_score,
     AVG(sats.avgscrwrite) as avg_write_score,
     COUNT(*) as record_count
     FROM satscores sats
     JOIN schools s ON sats.cds = s.cdscode
     WHERE sats.enroll12 IS NOT NULL;
