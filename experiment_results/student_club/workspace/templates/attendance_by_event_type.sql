SELECT e.type, COUNT(at.link_to_member) as total_attendances FROM attendance at JOIN event e ON at.link_to_event = e.event_id GROUP BY e.type ORDER BY total_attendances DESC;
