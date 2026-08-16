SELECT e.type, COUNT(DISTINCT a.link_to_member) as attendance_count FROM event e JOIN attendance a ON e.event_id = a.link_to_event GROUP BY e.type ORDER BY attendance_count DESC LIMIT 10;
