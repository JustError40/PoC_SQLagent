-- candidate template learned from payment-event trajectories
SELECT date_trunc('month', paid_at)::date AS month,
       round(sum(amount)::numeric, 2) AS revenue
FROM order_payments
WHERE status IN ('captured', 'partial')
GROUP BY 1 ORDER BY 1;
