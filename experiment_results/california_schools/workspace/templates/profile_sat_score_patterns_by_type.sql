SELECT rtype, AVG(avgscrread) as avg_read, AVG(avgscrmath) as avg_math, AVG(avgscrwrite) as avg_write, COUNT(*) as total_records FROM satscores GROUP BY rtype ORDER BY rtype;
