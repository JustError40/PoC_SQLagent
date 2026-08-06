SELECT sr_store_sk, SUM(sr_return_amt) AS total_return FROM store_returns GROUP BY sr_store_sk;
