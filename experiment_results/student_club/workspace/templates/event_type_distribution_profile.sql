SELECT event.type, COUNT(*) as event_count FROM event GROUP BY event.type ORDER BY event_count DESC;
