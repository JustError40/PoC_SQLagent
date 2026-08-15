WITH product_segment AS (
    SELECT
        t.productid,
        p.description,
        c.segment,
        c.currency,
        COUNT(*) as transaction_count,
        SUM(t.amount) as total_value
    FROM transactions_1k t
    JOIN products p ON t.productid = p.productid
    JOIN customers c ON t.customerid = c.customerid
    GROUP BY t.productid, p.description, c.segment, c.currency
)
SELECT
    segment,
    currency,
    COUNT(DISTINCT productid) as product_count,
    SUM(transaction_count) as total_transactions,
    SUM(total_value) as total_value
FROM product_segment
GROUP BY segment, currency
ORDER BY total_value DESC
LIMIT 10;
