import csv
import json
import sys
import os
import psycopg2
import psycopg2.extras

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


def create_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id              TEXT PRIMARY KEY,
        customer_name         TEXT,
        status                TEXT,
        carrier               TEXT,
        tracking_number       TEXT,
        estimated_delivery    TEXT,
        items                 JSONB NOT NULL DEFAULT '[]',
        shipping_mode         TEXT,
        order_region          TEXT,
        order_country         TEXT,
        order_city            TEXT,
        market                TEXT,
        late_delivery_risk    INTEGER DEFAULT 0,
        benefit_per_order     FLOAT,
        sales_per_customer    FLOAT,
        order_date            TEXT
    );

    CREATE TABLE IF NOT EXISTS tracking_events (
        tracking_number              TEXT PRIMARY KEY,
        carrier                      TEXT,
        current_location             TEXT,
        status                       TEXT,
        last_update                  TEXT,
        estimated_delivery           TEXT,
        events                       JSONB NOT NULL DEFAULT '[]',
        days_for_shipping_real       INTEGER,
        days_for_shipment_scheduled  INTEGER,
        delivery_status              TEXT,
        shipping_date                TEXT,
        latitude                     FLOAT,
        longitude                    FLOAT
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Tables created successfully.")


def seed_orders():
    filepath = os.path.join(os.path.dirname(__file__), "orders.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        rows   = list(reader)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO orders
                        (order_id, customer_name, status, carrier, tracking_number,
                         estimated_delivery, items, shipping_mode, order_region,
                         order_country, order_city, market, late_delivery_risk,
                         benefit_per_order, sales_per_customer, order_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (order_id) DO NOTHING
                    """,
                    [
                        row["order_id"],
                        row["customer_name"],
                        row["status"],
                        row["carrier"],
                        row["tracking_number"],
                        row["estimated_delivery"],
                        psycopg2.extras.Json(json.loads(row["items"])),
                        row["shipping_mode"],
                        row["order_region"],
                        row["order_country"],
                        row["order_city"],
                        row["market"],
                        int(row["late_delivery_risk"]),
                        float(row["benefit_per_order"]),
                        float(row["sales_per_customer"]),
                        row["order_date"],
                    ]
                )
    print(f"Seeded {len(rows)} orders.")


def seed_tracking_events():
    filepath = os.path.join(os.path.dirname(__file__), "tracking_events.csv")
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        rows   = list(reader)

    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO tracking_events
                        (tracking_number, carrier, current_location, status,
                         last_update, estimated_delivery, events,
                         days_for_shipping_real, days_for_shipment_scheduled,
                         delivery_status, shipping_date, latitude, longitude)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tracking_number) DO NOTHING
                    """,
                    [
                        row["tracking_number"],
                        row["carrier"],
                        row["current_location"],
                        row["status"],
                        row["last_update"],
                        row["estimated_delivery"],
                        psycopg2.extras.Json(json.loads(row["events"])),
                        int(row["days_for_shipping_real"]),
                        int(row["days_for_shipment_scheduled"]),
                        row["delivery_status"],
                        row["shipping_date"],
                        float(row["latitude"]),
                        float(row["longitude"]),
                    ]
                )
    print(f"Seeded {len(rows)} tracking records.")


if __name__ == "__main__":
    print("Starting database seeding...")
    create_tables()
    seed_orders()
    seed_tracking_events()
    print("Done. Database seeded successfully.")