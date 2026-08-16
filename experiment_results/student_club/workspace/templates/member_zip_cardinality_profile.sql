SELECT z.zip_code, COUNT(m.member_id) AS member_count FROM member m JOIN zip_code z ON m.zip = z.zip_code GROUP BY z.zip_code ORDER BY member_count DESC;
