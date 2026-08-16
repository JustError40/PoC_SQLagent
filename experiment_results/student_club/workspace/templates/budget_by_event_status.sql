SELECT e.status, SUM(b.spent) as total_spent, COUNT(b.budget_id) as budget_count FROM budget b JOIN event e ON b.link_to_event = e.event_id GROUP BY e.status ORDER BY total_spent DESC;
