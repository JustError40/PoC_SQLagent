SELECT event_status, COUNT(*) as budget_count FROM budget GROUP BY event_status ORDER BY budget_count DESC;
