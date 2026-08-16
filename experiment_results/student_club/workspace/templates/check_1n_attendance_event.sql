SELECT e.event_id, COUNT(a.link_to_member) as attendance_count FROM event e INNER JOIN attendance a ON a.link_to_event = e.event_id GROUP BY e.event_id ORDER BY attendance_count DESC LIMIT 100;
