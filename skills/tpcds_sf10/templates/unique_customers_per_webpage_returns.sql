SELECT wp.wp_web_page_sk, COUNT(DISTINCT wr.wr_returning_customer_sk) AS unique_customers FROM web_returns wr JOIN web_page wp ON wr.wr_web_page_sk = wp.wp_web_page_sk GROUP BY wp.wp_web_page_sk;
