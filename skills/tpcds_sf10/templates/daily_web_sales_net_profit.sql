SELECT t.d_date, SUM(ws.ws_net_profit) AS daily_total FROM web_sales ws JOIN date_dim t ON ws.ws_sold_date_sk = t.d_date_sk GROUP BY t.d_date ORDER BY t.d_date;
