SELECT e.type, SUM(b.spent) as total_spent, COUNT(DISTINCT b.link_to_event) as budget_records FROM budget b JOIN event e ON b.link_to_event = e.event_id GROUP BY e.type ORDER BY total_spent DESC;
