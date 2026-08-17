SELECT COUNT(*) as numge1500_count, rtype FROM satscores WHERE numge1500 IS NOT NULL GROUP BY rtype;
