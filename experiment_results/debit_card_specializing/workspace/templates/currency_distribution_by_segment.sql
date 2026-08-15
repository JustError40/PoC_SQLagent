SELECT c.segment, c.currency, COUNT(*) as customer_count FROM customers c GROUP BY c.segment, c.currency ORDER BY customer_count DESC;
