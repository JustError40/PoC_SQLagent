SELECT COUNT(*) FROM web_returns wr LEFT JOIN web_page wp ON wr.wr_web_page_sk = wp.wp_web_page_sk WHERE wp.wp_web_page_sk IS NULL;
