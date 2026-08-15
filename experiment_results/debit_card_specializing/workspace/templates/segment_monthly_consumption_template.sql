WITH monthly_segment_consumption AS (
    SELECT
        c.segment,
        ym.date,
        SUM(ym.consumption) as total_consumption,
        COUNT(DISTINCT ym.customerid) as unique_customers
    FROM yearmonth ym
    JOIN customers c ON ym.customerid = c.customerid
    GROUP BY c.segment, ym.date
)
SELECT * FROM monthly_segment_consumption;
