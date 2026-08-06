SELECT AVG(cr_return_amount) AS avg_return, r.r_reason_desc FROM catalog_returns cr JOIN reason r ON cr.cr_reason_sk = r.r_reason_sk GROUP BY r.r_reason_desc;
