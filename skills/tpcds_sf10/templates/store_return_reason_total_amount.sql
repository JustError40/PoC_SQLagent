SELECT sr_reason_sk, SUM(sr_return_amt) AS total_return_amount FROM store_returns GROUP BY sr_reason_sk;
