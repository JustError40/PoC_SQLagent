SELECT m2.major_name, COUNT(m.member_id) AS member_count FROM member m JOIN major m2 ON m.link_to_major = m2.major_id GROUP BY m2.major_name ORDER BY member_count DESC;
