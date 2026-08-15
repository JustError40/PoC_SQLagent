SELECT rtype, avg(avgscrread) as avg_read, avg(avgscrmath) as avg_math, avg(avgscrwrite) as avg_write, count(*) as record_count FROM satscores GROUP BY rtype ORDER BY record_count DESC;
