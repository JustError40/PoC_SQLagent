from __future__ import annotations

import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db_seed" / "schema.sql"
DEFAULT_DSN = "postgresql://warehouse@localhost:5432/warehouse"


def seed_database(dsn: str | None = None, orders: int | None = None) -> dict[str, int]:
    """Recreate and fill the synthetic warehouse with stable, set-based SQL."""

    dsn = dsn or os.getenv("DATABASE_URL", DEFAULT_DSN)
    order_count = orders or int(os.getenv("SEED_ORDERS", "50000"))
    if not 1 <= order_count <= 2_000_000:
        raise ValueError("SEED_ORDERS must be between 1 and 2,000,000")

    with psycopg.connect(dsn) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("SELECT setseed(0.314159)")

        conn.execute(
            """
            INSERT INTO customers (id, signup_date, segment, region, is_deleted)
            SELECT g, DATE '2023-01-01' + ((g * 19) % 700),
                   (ARRAY['new','returning','enterprise','smb'])[1 + (g % 4)],
                   (ARRAY['north','south','east','west','central'])[1 + (g % 5)],
                   g % 97 = 0
            FROM generate_series(1, 5000) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO products (id, name, category, price, cost)
            SELECT g, 'Product ' || lpad(g::text, 4, '0'),
                   (ARRAY['electronics','home','grocery','apparel','sports','beauty'])[1 + (g % 6)],
                   round((10 + (g * 7 % 900) + random() * 50)::numeric, 2),
                   round((5 + (g * 5 % 450) + random() * 20)::numeric, 2)
            FROM generate_series(1, 300) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO stores (id, name, region, opened_on)
            SELECT g, 'Store ' || g,
                   (ARRAY['north','south','east','west','central'])[1 + (g % 5)],
                   DATE '2018-01-01' + ((g * 41) % 1000)
            FROM generate_series(1, 25) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO marketing_campaigns (id, name, channel, starts_on, ends_on)
            SELECT g, 'Campaign ' || g,
                   (ARRAY['search','social','email','partner','display'])[1 + (g % 5)],
                   DATE '2024-01-01' + ((g * 29) % 600),
                   DATE '2024-01-15' + ((g * 29) % 600)
            FROM generate_series(1, 30) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO employees (id, store_id, role, hired_on)
            SELECT g, 1 + (g % 25),
                   (ARRAY['sales','manager','support','warehouse'])[1 + (g % 4)],
                   DATE '2020-01-01' + ((g * 13) % 1400)
            FROM generate_series(1, 150) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO suppliers (id, name, country)
            SELECT g, 'Supplier ' || g,
                   (ARRAY['RU','DE','CN','TR','KZ'])[1 + (g % 5)]
            FROM generate_series(1, 60) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO product_suppliers (product_id, supplier_id, lead_days)
            SELECT p, 1 + ((p * 7) % 60), 2 + ((p * 11) % 30)
            FROM generate_series(1, 300) AS s(p)
            UNION ALL
            SELECT p, 1 + ((p * 13 + 3) % 60), 4 + ((p * 5) % 25)
            FROM generate_series(1, 300) AS s(p)
            """
        )
        conn.execute(
            """
            INSERT INTO orders (id, customer_id, store_id, order_date, status, total_amount, is_deleted)
            SELECT g, 1 + ((g * 23) %% 5000), 1 + ((g * 7) %% 25),
                   DATE '2024-01-01' + ((g * 37) %% 730),
                   (ARRAY['paid','paid','paid','shipped','delivered','cancelled'])[1 + (g %% 6)],
                   round((25 + ((g * 31) %% 900) + random() * 120)::numeric, 2),
                   g %% 211 = 0
            FROM generate_series(1, %s) AS s(g)
            """,
            (order_count,),
        )
        conn.execute(
            """
            INSERT INTO order_items (id, order_id, order_date, product_id, quantity, unit_price)
            SELECT o.id * 10 + item_no, o.id, o.order_date,
                   1 + ((o.id * 17 + item_no * 3) % 300),
                   1 + ((o.id + item_no * 5) % 4),
                   round((15 + ((o.id * 19 + item_no * 7) % 800) + random() * 30)::numeric, 2)
            FROM orders o
            CROSS JOIN LATERAL generate_series(1, 1 + (o.id % 5)) AS items(item_no)
            """
        )
        conn.execute(
            """
            INSERT INTO order_payments (id, order_id, order_date, paid_at, amount, status)
            SELECT o.id * 10 + payment_no, o.id, o.order_date,
                   o.order_date + (payment_no || ' days')::interval,
                   round((o.total_amount / CASE WHEN payment_no = 2 THEN 2 ELSE 1 END)::numeric, 2),
                   CASE WHEN o.status = 'cancelled' THEN 'refunded'
                        WHEN payment_no = 2 THEN 'partial' ELSE 'captured' END
            FROM orders o
            CROSS JOIN LATERAL generate_series(1, CASE WHEN o.id % 7 = 0 THEN 2 ELSE 1 END) AS p(payment_no)
            """
        )
        conn.execute(
            """
            INSERT INTO shipments (id, order_id, order_date, shipped_at, delivered_at, carrier, status)
            SELECT o.id, o.id, o.order_date,
                   CASE WHEN o.status IN ('shipped','delivered') THEN o.order_date + interval '1 day' END,
                   CASE WHEN o.status = 'delivered' THEN o.order_date + interval '4 days' END,
                   (ARRAY['cdek','dhl','boxberry','pickup'])[1 + (o.id % 4)],
                   CASE WHEN o.status = 'cancelled' THEN 'cancelled' ELSE o.status END
            FROM orders o
            """
        )
        conn.execute(
            """
            INSERT INTO returns (id, order_id, order_date, product_id, quantity, reason)
            SELECT o.id, o.id, o.order_date, 1 + ((o.id * 17) % 300), 1,
                   (ARRAY['damaged','wrong_size','changed_mind'])[1 + (o.id % 3)]
            FROM orders o WHERE o.id % 29 = 0 AND o.status <> 'cancelled'
            """
        )
        conn.execute(
            """
            INSERT INTO customer_campaigns (customer_id, campaign_id, acquired_at)
            SELECT c.id, 1 + ((c.id * 3) % 30), c.signup_date
            FROM customers c WHERE c.id % 2 = 0
            """
        )
        conn.execute(
            """
            INSERT INTO inventory_snapshots (id, product_id, snapshot_date, warehouse, on_hand, reorder_point)
            SELECT p * 100 + m, p, DATE '2024-01-01' + (m * 30),
                   (ARRAY['Moscow','Kazan','Novosibirsk'])[1 + (p % 3)],
                   10 + ((p * 17 + m * 31) % 500), 20 + ((p * 7) % 100)
            FROM generate_series(1, 300) AS products(p)
            CROSS JOIN generate_series(0, 23) AS months(m)
            """
        )
        conn.execute(
            """
            INSERT INTO expenses (id, store_id, expense_date, category, amount)
            SELECT g, 1 + (g % 25), DATE '2024-01-01' + (g % 730),
                   (ARRAY['rent','payroll','marketing','utilities'])[1 + (g % 4)],
                   round((100 + (g * 23 % 3000) + random() * 100)::numeric, 2)
            FROM generate_series(1, 18000) AS s(g)
            """
        )
        conn.execute(
            """
            INSERT INTO daily_fx_rates (rate_date, currency, rate)
            SELECT DATE '2024-01-01' + d, currency,
                   round((1 + ((d * 13 + c * 7) % 30) / 100.0)::numeric, 6)
            FROM generate_series(0, 729) AS days(d)
            CROSS JOIN generate_series(1, 3) AS currencies(c)
            CROSS JOIN LATERAL (VALUES (CASE c WHEN 1 THEN 'USD' WHEN 2 THEN 'EUR' ELSE 'CNY' END)) AS v(currency)
            """
        )
        conn.execute("ANALYZE")

        counts = {}
        for table in ("customers", "products", "orders", "order_items", "order_payments", "shipments"):
            counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        conn.commit()
        return counts


if __name__ == "__main__":
    print(seed_database())
