SELECT sr_store_sk, AVG(sr_return_amt) AS avg_return FROM store_returns GROUP BY sr_store_sk;
