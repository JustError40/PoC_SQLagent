SELECT p.category, round(sum(i.quantity * i.unit_price)::numeric, 2) AS revenue
FROM order_items i
JOIN products p ON p.id = i.product_id
GROUP BY p.category ORDER BY revenue DESC;
