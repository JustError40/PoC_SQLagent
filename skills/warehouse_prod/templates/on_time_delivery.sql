SELECT round(100.0 * avg((delivered_at <= shipped_at + interval '5 days')::int), 2) AS on_time_percent
FROM shipments WHERE status = 'delivered';
