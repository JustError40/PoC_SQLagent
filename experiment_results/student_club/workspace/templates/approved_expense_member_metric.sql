WITH approved_expenses AS (
  SELECT
    expense.link_to_member,
    expense.cost,
    expense.approved
  FROM expense
  WHERE expense.approved::boolean = TRUE
)
SELECT
  m.member_id,
  m.first_name,
  m.last_name,
  SUM(ae.cost) as total_approved_expenses,
  COUNT(*) as approved_expense_count
FROM approved_expenses ae
INNER JOIN member m ON ae.link_to_member = m.member_id
GROUP BY m.member_id, m.first_name, m.last_name
ORDER BY total_approved_expenses DESC
LIMIT 10;
