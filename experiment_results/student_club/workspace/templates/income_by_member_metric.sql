SELECT i.link_to_member, COUNT(*) as transaction_count, SUM(i.amount) as total_income FROM income i GROUP BY i.link_to_member HAVING COUNT(*) >= 1 ORDER BY total_income DESC;
