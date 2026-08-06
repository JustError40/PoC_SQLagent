SELECT COUNT(*) AS total, SUM(CASE WHEN cd_purchase_estimate IS NOT NULL THEN 1 ELSE 0 END) FROM customer_demographics;
