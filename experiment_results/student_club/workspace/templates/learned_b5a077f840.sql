SELECT m.first_name, m.last_name, i.amount FROM member m INNER JOIN income i ON m.member_id = i.link_to_member WHERE i.date_received = '2019-09-09';
