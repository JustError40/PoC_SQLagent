SELECT e.expense_id, e.link_to_member, e.cost,
       b.category,
       b.amount AS budget_amount,
       b.spent AS budget_spent
FROM expense e
JOIN member m ON e.link_to_member = m.member_id
JOIN budget b ON e.link_to_budget = b.budget_id
WHERE e.approved = 'true';
