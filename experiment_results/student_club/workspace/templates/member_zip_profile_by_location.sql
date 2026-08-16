SELECT z.zip_code, z.city, z.state, COUNT(m.member_id) as member_count FROM zip_code z INNER JOIN member m ON z.zip_code = m.zip GROUP BY z.zip_code, z.city, z.state ORDER BY member_count DESC;
