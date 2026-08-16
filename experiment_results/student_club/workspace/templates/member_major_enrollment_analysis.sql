SELECT m.major_name, COUNT(DISTINCT mem.member_id) as member_count FROM member mem JOIN major m ON mem.link_to_major = m.major_id GROUP BY m.major_name ORDER BY member_count DESC;
