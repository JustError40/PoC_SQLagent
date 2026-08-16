SELECT m_major.major_name, COUNT(m.member_id) AS member_count FROM member m INNER JOIN major m_major ON m.link_to_major = m_major.major_id GROUP BY m_major.major_name ORDER BY member_count DESC;
