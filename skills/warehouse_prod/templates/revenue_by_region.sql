SELECT s.region, round(sum(o.total_amount)::numeric, 2) AS revenue
FROM orders o JOIN stores s ON s.id = o.store_id
WHERE NOT o.is_deleted AND o.status <> 'cancelled'
GROUP BY s.region ORDER BY revenue DESC;
