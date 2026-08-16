SELECT e.event_id, COUNT(DISTINCT a.link_to_member) AS member_count FROM event e INNER JOIN attendance a ON e.event_id = a.link_to_event GROUP BY e.event_id ORDER BY member_count DESC LIMIT 10;
