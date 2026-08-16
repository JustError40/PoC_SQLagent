SELECT CASE WHEN cost < 50 THEN 'low' WHEN cost < 200 THEN 'medium' ELSE 'high' END as cost_tier, COUNT(*) as count, AVG(cost) as avg_cost FROM expense GROUP BY cost_tier ORDER BY avg_cost DESC;
