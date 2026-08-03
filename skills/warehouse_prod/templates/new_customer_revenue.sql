WITH first_orders AS (
  SELECT customer_id, min(order_date) AS first_order_date
  FROM orders WHERE NOT is_deleted AND status <> 'cancelled'
  GROUP BY customer_id
)
SELECT date_trunc('month', o.order_date)::date AS month,
       round(sum(o.total_amount)::numeric, 2) AS revenue
FROM orders o
JOIN first_orders f ON f.customer_id = o.customer_id
  AND f.first_order_date = o.order_date
WHERE NOT o.is_deleted AND o.status <> 'cancelled'
GROUP BY 1 ORDER BY 1;
