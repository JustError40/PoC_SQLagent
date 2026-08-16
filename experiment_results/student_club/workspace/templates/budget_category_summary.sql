SELECT category, SUM(amount) AS total_initial_budget, SUM(spent) AS total_spent FROM budget GROUP BY category ORDER BY total_initial_budget DESC;
