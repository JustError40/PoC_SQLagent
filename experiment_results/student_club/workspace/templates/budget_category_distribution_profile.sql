SELECT budget.category, COUNT(*) as budget_count, SUM(budget.spent) as total_spent FROM budget GROUP BY budget.category ORDER BY total_spent DESC;
