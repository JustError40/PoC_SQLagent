SELECT ds.d_date AS day,
       s.state_name AS state,
       SUM(ws.net_sales) - SUM(ds.discount_amount) AS daily_net_profit
FROM date_dim ds
JOIN web_sales ws ON ws.date_key = ds.d_date_sk
JOIN store s ON s.store_id = ws.store_id
GROUP BY ds.d_date, s.state_name
ORDER BY day;
