SELECT event_status, COUNT(*) as count, SUM(spent) as total_spent, SUM(remaining) as total_remaining FROM budget GROUP BY event_status ORDER BY total_spent DESC;
