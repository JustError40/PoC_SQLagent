SELECT r.r_reason_desc, SUM(sr.sr_return_amt) AS total_amount FROM store_returns sr JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk GROUP BY r.r_reason_desc;
