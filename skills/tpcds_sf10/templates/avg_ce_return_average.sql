SELECT AVG(cr_net_loss) AS avg_net_loss, cr_returning_customer_sk FROM catalog_returns GROUP BY cr_returning_customer_sk;
