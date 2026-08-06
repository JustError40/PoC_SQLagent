WITH sales AS (
  SELECT cs.net_profit AS ap_net_profit, cs_ship_date_sk
  FROM catalog_sales cs
  JOIN stores s ON cs_store_sk = s.sk
  WHERE cs_ship_date_sk IS NOT NULL AND cs_shipping_completed IS TRUE
)
SELECT EXTRACT(YEAR FROM cs_ship_date_sk) AS year,
       SUM(ap_net_profit) AS revenue
FROM sales
GROUP BY EXTRACT(YEAR FROM cs_ship_date_sk);
