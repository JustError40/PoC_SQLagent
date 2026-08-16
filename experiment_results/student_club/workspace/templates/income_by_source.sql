SELECT i.source, SUM(i.amount) AS total_amount, COUNT(*) AS transaction_count FROM income i JOIN member m ON i.link_to_member = m.member_id GROUP BY i.source ORDER BY total_amount DESC;
