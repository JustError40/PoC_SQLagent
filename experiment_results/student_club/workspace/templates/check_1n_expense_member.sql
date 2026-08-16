SELECT m.member_id, COUNT(e.expense_id) as expense_count FROM member m INNER JOIN expense e ON e.link_to_member = m.member_id GROUP BY m.member_id ORDER BY expense_count DESC LIMIT 100;
