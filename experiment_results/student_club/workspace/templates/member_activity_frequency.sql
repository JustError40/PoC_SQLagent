SELECT link_to_member, COUNT(DISTINCT link_to_event) as event_count, COUNT(*) as attendance_count FROM attendance GROUP BY link_to_member ORDER BY event_count DESC LIMIT 30;
