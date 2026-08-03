CREATE TABLE customers (
    id integer PRIMARY KEY,
    signup_date date NOT NULL,
    segment text NOT NULL,
    region text NOT NULL,
    is_deleted boolean NOT NULL DEFAULT false
);

CREATE TABLE products (
    id integer PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2) NOT NULL,
    cost numeric(12, 2) NOT NULL
);

CREATE TABLE stores (
    id integer PRIMARY KEY,
    name text NOT NULL,
    region text NOT NULL,
    opened_on date NOT NULL
);

CREATE TABLE orders (
    id bigint NOT NULL,
    customer_id integer NOT NULL REFERENCES customers(id),
    store_id integer NOT NULL REFERENCES stores(id),
    order_date date NOT NULL,
    status text NOT NULL,
    total_amount numeric(14, 2) NOT NULL,
    is_deleted boolean NOT NULL DEFAULT false,
    PRIMARY KEY (id, order_date)
) PARTITION BY RANGE (order_date);

CREATE TABLE orders_2024 PARTITION OF orders FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE orders_2025 PARTITION OF orders FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE orders_2026 PARTITION OF orders FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE order_items (
    id bigint PRIMARY KEY,
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    product_id integer NOT NULL REFERENCES products(id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL
);

CREATE TABLE order_payments (
    id bigint PRIMARY KEY,
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    paid_at timestamptz NOT NULL,
    amount numeric(14, 2) NOT NULL,
    status text NOT NULL
);

CREATE TABLE shipments (
    id bigint PRIMARY KEY,
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    shipped_at timestamptz,
    delivered_at timestamptz,
    carrier text NOT NULL,
    status text NOT NULL
);

CREATE TABLE returns (
    id bigint PRIMARY KEY,
    order_id bigint NOT NULL,
    order_date date NOT NULL,
    product_id integer NOT NULL REFERENCES products(id),
    quantity integer NOT NULL,
    reason text NOT NULL
);

CREATE TABLE marketing_campaigns (
    id integer PRIMARY KEY,
    name text NOT NULL,
    channel text NOT NULL,
    starts_on date NOT NULL,
    ends_on date NOT NULL
);

CREATE TABLE customer_campaigns (
    customer_id integer NOT NULL REFERENCES customers(id),
    campaign_id integer NOT NULL REFERENCES marketing_campaigns(id),
    acquired_at date NOT NULL,
    PRIMARY KEY (customer_id, campaign_id)
);

CREATE TABLE employees (
    id integer PRIMARY KEY,
    store_id integer NOT NULL REFERENCES stores(id),
    role text NOT NULL,
    hired_on date NOT NULL
);

CREATE TABLE suppliers (
    id integer PRIMARY KEY,
    name text NOT NULL,
    country text NOT NULL
);

CREATE TABLE product_suppliers (
    product_id integer NOT NULL REFERENCES products(id),
    supplier_id integer NOT NULL REFERENCES suppliers(id),
    lead_days integer NOT NULL,
    PRIMARY KEY (product_id, supplier_id)
);

CREATE TABLE inventory_snapshots (
    id bigint PRIMARY KEY,
    product_id integer NOT NULL REFERENCES products(id),
    snapshot_date date NOT NULL,
    warehouse text NOT NULL,
    on_hand integer NOT NULL,
    reorder_point integer NOT NULL
);

CREATE TABLE expenses (
    id bigint PRIMARY KEY,
    store_id integer NOT NULL REFERENCES stores(id),
    expense_date date NOT NULL,
    category text NOT NULL,
    amount numeric(14, 2) NOT NULL
);

CREATE TABLE daily_fx_rates (
    rate_date date NOT NULL,
    currency text NOT NULL,
    rate numeric(12, 6) NOT NULL,
    PRIMARY KEY (rate_date, currency)
);

CREATE INDEX orders_customer_date_idx ON orders (customer_id, order_date);
CREATE INDEX orders_status_date_idx ON orders (status, order_date);
CREATE INDEX order_items_order_idx ON order_items (order_id, order_date);
CREATE INDEX order_items_product_idx ON order_items (product_id);
CREATE INDEX order_payments_order_idx ON order_payments (order_id, order_date);
CREATE INDEX shipments_order_idx ON shipments (order_id, order_date);
CREATE INDEX inventory_product_date_idx ON inventory_snapshots (product_id, snapshot_date);

