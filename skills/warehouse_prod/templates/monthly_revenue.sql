-- order grain: do not join order_payments or order_items for this metric
SELECT date_trunc('month', order_date)::date AS month,
       round(sum(total_amount)::numeric, 2) AS revenue
FROM orders
WHERE NOT is_deleted AND status <> 'cancelled'
GROUP BY 1 ORDER BY 1;
