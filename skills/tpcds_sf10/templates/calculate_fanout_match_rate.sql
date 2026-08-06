SELECT AVG(CASE WHEN cs_bill_cdemo_sk = cd_demo_sk THEN 1 ELSE 0 END) AS match_rate FROM catalog_sales LEFT JOIN customer_demographics ON cs_bill_cdemo_sk = cd_demo_sk;
