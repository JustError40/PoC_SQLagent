SELECT e.event_id, COUNT(b.budget_id) as budget_count FROM budget b JOIN event e ON b.link_to_event = e.event_id GROUP BY e.event_id ORDER BY budget_count DESC LIMIT 20;
