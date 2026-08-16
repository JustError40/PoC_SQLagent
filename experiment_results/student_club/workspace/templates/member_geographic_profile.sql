SELECT z.state, z.short_state, COUNT(m.member_id) as member_count FROM member m JOIN zip_code z ON m.zip = z.zip_code GROUP BY z.state, z.short_state ORDER BY member_count DESC;
