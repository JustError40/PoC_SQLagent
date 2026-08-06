SELECT AVG(cs.cs_net_profit) AS avg_np FROM catalog_sales cs LEFT JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk;
