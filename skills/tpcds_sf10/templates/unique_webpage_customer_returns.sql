SELECT COUNT(DISTINCT wr_returning_customer_sk) AS unique_website_returns FROM web_returns WHERE wr_web_page_sk IS NOT NULL;
