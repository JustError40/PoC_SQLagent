SELECT zip, COUNT(DISTINCT m.member_id) as member_count FROM member m JOIN zip_code z ON m.zip = z.zip_code GROUP BY zip ORDER BY member_count DESC LIMIT 10;
