SELECT zip, COUNT(*) as member_count FROM member WHERE zip IS NOT NULL GROUP BY zip ORDER BY member_count DESC LIMIT 20;
