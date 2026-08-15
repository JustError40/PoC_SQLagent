WITH monthly_consumption AS (
  SELECT ym.customerid, ym.date, c.segment, SUM(ym.consumption) as total_consumption, COUNT(*) as month_count
  FROM yearmonth ym
  JOIN customers c ON ym.customerid = c.customerid
  GROUP BY ym.customerid, ym.date, c.segment
)
SELECT segment, date, total_consumption, month_count FROM monthly_consumption ORDER BY date, segment;
