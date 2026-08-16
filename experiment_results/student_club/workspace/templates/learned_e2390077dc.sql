SELECT m.first_name, m.last_name FROM member m JOIN attendance a ON m.member_id = a.link_to_member GROUP BY m.first_name, m.last_name HAVING COUNT(a.link_to_event) > 7;
