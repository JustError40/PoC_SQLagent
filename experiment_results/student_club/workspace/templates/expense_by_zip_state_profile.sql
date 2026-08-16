SELECT z.state, SUM(e.cost) as total_expenses FROM expense e JOIN member m ON e.link_to_member = m.member_id JOIN zip_code z ON m.zip = z.zip_code GROUP BY z.state ORDER BY total_expenses DESC;
