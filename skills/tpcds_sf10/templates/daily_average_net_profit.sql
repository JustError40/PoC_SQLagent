SELECT AVG(cs_net_profit) AS avg_daily_net_profit, COUNT(*) AS cnt FROM catalog_sales WHERE cs_ship_customer_sk IS NOT NULL GROUP BY cs_sold_date_sk;
