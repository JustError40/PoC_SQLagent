WITH consumption_trend AS (
  SELECT
    customerid,
    date,
    consumption,
    LAG(consumption) OVER (PARTITION BY customerid ORDER BY date) AS prev_consumption,
    CASE
      WHEN LAG(consumption) OVER (PARTITION BY customerid ORDER BY date) IS NOT NULL
        THEN (consumption - LAG(consumption) OVER (PARTITION BY customerid ORDER BY date)) / NULLIF(LAG(consumption) OVER (PARTITION BY customerid ORDER BY date), 0)
      ELSE NULL
    END AS month_over_month_change
  FROM yearmonth
  WHERE date IS NOT NULL
)
SELECT customerid, date, consumption, month_over_month_change FROM consumption_trend WHERE month_over_month_change IS NOT NULL;
