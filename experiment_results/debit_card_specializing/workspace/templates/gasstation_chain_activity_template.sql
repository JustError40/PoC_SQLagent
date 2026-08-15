WITH chain_activity AS (
  SELECT
    g.chainid,
    COUNT(DISTINCT t.customerid) as unique_customers,
    COUNT(*) as transaction_count,
    SUM(t.amount) as total_spending,
    AVG(t.amount) as avg_transaction_amount
  FROM gasstations g
  INNER JOIN transactions_1k t ON g.gasstationid = t.gasstationid
  GROUP BY g.chainid
)
SELECT * FROM chain_activity ORDER BY total_spending DESC LIMIT 50;
