SELECT sr_reason_sk, AVG(sr_return_amt) AS avg_return_amount FROM store_returns GROUP BY sr_reason_sk;
