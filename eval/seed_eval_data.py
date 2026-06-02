"""
Seed eval_user and all required data for the evaluation pipeline.
Run this before running eval/run_eval.py to ensure a clean eval state.

Usage:
    POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=multiagent \
    POSTGRES_USER=postgres POSTGRES_PASSWORD=1234 \
    python eval/seed_eval_data.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402
from config import config  # noqa: E402


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


EVAL_USER = "eval_user"

# The 6 orders the eval dataset references
EVAL_ORDERS = [
    {
        "order_id": "ORD1401",
        "customer_name": "Apoorva S B",
        "status": "DELIVERED",
        "carrier": "Ekart",
        "tracking_number": "EK101401",
        "estimated_delivery": "2024-01-06",
        "items": ["Hard Drive"],
        "shipping_mode": "Standard Class",
        "order_city": "Bangalore",
        "order_date": "2024-01-05",
        "lat": 12.9716,
        "lon": 77.5946,
    },
    {
        "order_id": "ORD1419",
        "customer_name": "Apoorva S B",
        "status": "IN_TRANSIT",
        "carrier": "FedEx",
        "tracking_number": "FX101419",
        "estimated_delivery": "2024-04-11",
        "items": ["Laptop Bag"],
        "shipping_mode": "Standard Class",
        "order_city": "Mumbai",
        "order_date": "2024-04-08",
        "lat": 19.0760,
        "lon": 72.8777,
    },
    {
        "order_id": "ORD1437",
        "customer_name": "Apoorva S B",
        "status": "PENDING",
        "carrier": "Delhivery",
        "tracking_number": "DL101437",
        "estimated_delivery": "2024-06-08",
        "items": ["RAM", "SSD"],
        "shipping_mode": "Standard Class",
        "order_city": "Pune",
        "order_date": "2024-06-07",
        "lat": 18.5204,
        "lon": 73.8567,
    },
    {
        "order_id": "ORD1455",
        "customer_name": "Apoorva S B",
        "status": "DELIVERED",
        "carrier": "Delhivery",
        "tracking_number": "DL101455",
        "estimated_delivery": "2024-03-05",
        "items": ["Smartphone"],
        "shipping_mode": "Standard Class",
        "order_city": "Chennai",
        "order_date": "2024-02-29",
        "lat": 13.0827,
        "lon": 80.2707,
    },
    {
        "order_id": "ORD1473",
        "customer_name": "Apoorva S B",
        "status": "OUT_FOR_DELIVERY",
        "carrier": "Delhivery",
        "tracking_number": "DL101473",
        "estimated_delivery": "2024-04-23",
        "items": ["Books"],
        "shipping_mode": "Standard Class",
        "order_city": "Delhi",
        "order_date": "2024-04-18",
        "lat": 28.7041,
        "lon": 77.1025,
    },
    {
        "order_id": "ORD1491",
        "customer_name": "Apoorva S B",
        "status": "IN_TRANSIT",
        "carrier": "Delhivery",
        "tracking_number": "DL101491",
        "estimated_delivery": "2024-05-28",
        "items": ["Motherboard"],
        "shipping_mode": "Standard Class",
        "order_city": "Hyderabad",
        "order_date": "2024-05-25",
        "lat": 17.3850,
        "lon": 78.4867,
    },
]

TRACKING_EVENTS = {
    "EK101401": {
        "carrier": "Ekart",
        "location": "Bangalore Hub",
        "status": "DELIVERED",
        "last_update": "2024-01-06T10:00:00Z",
        "eta": "2024-01-06T00:00:00Z",
        "events": [
            {"time": "2024-01-05T10:00:00Z", "status": "Order placed"},
            {"time": "2024-01-06T08:00:00Z", "status": "Picked up from seller"},
            {"time": "2024-01-06T09:00:00Z", "status": "Out for delivery"},
            {"time": "2024-01-06T10:00:00Z", "status": "Delivered"},
        ],
        "days_real": 1,
        "days_sched": 1,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-01-05",
    },
    "FX101419": {
        "carrier": "FedEx",
        "location": "Kolkata Gateway",
        "status": "IN_TRANSIT",
        "last_update": "2024-04-10T08:00:00Z",
        "eta": "2024-04-11T00:00:00Z",
        "events": [
            {"time": "2024-04-08T10:00:00Z", "status": "Order placed"},
            {"time": "2024-04-09T08:00:00Z", "status": "Picked up from seller"},
            {"time": "2024-04-10T08:00:00Z", "status": "In transit"},
        ],
        "days_real": 3,
        "days_sched": 3,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-04-09",
    },
    "DL101437": {
        "carrier": "Delhivery",
        "location": "Chennai Hub",
        "status": "PENDING",
        "last_update": "2024-06-07T10:00:00Z",
        "eta": "2024-06-08T00:00:00Z",
        "events": [
            {"time": "2024-06-07T10:00:00Z", "status": "Order placed"},
            {"time": "2024-06-07T12:00:00Z", "status": "Order received at warehouse"},
        ],
        "days_real": 1,
        "days_sched": 1,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-06-07",
    },
    "DL101455": {
        "carrier": "Delhivery",
        "location": "Mumbai Hub",
        "status": "DELIVERED",
        "last_update": "2024-03-05T11:00:00Z",
        "eta": "2024-03-05T00:00:00Z",
        "events": [
            {"time": "2024-02-29T10:00:00Z", "status": "Order placed"},
            {"time": "2024-03-01T08:00:00Z", "status": "Picked up from seller"},
            {"time": "2024-03-03T20:00:00Z", "status": "In transit"},
            {"time": "2024-03-05T09:00:00Z", "status": "Out for delivery"},
            {"time": "2024-03-05T11:00:00Z", "status": "Delivered"},
        ],
        "days_real": 5,
        "days_sched": 5,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-03-01",
    },
    "DL101473": {
        "carrier": "Delhivery",
        "location": "Delhi Distribution Center",
        "status": "OUT_FOR_DELIVERY",
        "last_update": "2024-04-23T08:00:00Z",
        "eta": "2024-04-23T00:00:00Z",
        "events": [
            {"time": "2024-04-18T10:00:00Z", "status": "Order placed"},
            {"time": "2024-04-19T08:00:00Z", "status": "Picked up from seller"},
            {"time": "2024-04-21T20:00:00Z", "status": "In transit"},
            {"time": "2024-04-23T08:00:00Z", "status": "Out for delivery"},
        ],
        "days_real": 5,
        "days_sched": 5,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-04-19",
    },
    "DL101491": {
        "carrier": "Delhivery",
        "location": "Chennai Hub",
        "status": "IN_TRANSIT",
        "last_update": "2024-05-26T08:00:00Z",
        "eta": "2024-05-28T00:00:00Z",
        "events": [
            {"time": "2024-05-25T10:00:00Z", "status": "Order placed"},
            {"time": "2024-05-26T08:00:00Z", "status": "Picked up from seller"},
            {"time": "2024-05-26T20:00:00Z", "status": "In transit"},
        ],
        "days_real": 3,
        "days_sched": 3,
        "delivery_status": "Advance shipping",
        "ship_date": "2024-05-26",
    },
}


def seed():
    with get_conn() as conn:
        with conn.cursor() as cur:

            # 1. Create eval_user
            cur.execute(
                "INSERT INTO users (user_id, created_at, metadata) "
                "VALUES (%s, NOW(), '{}') ON CONFLICT (user_id) DO NOTHING",
                [EVAL_USER],
            )

            # 2. Expire any active sessions for eval_user (clean state)
            cur.execute("UPDATE sessions SET is_active = false WHERE user_id = %s", [EVAL_USER])

            # 3. Remove any existing eval_user orders
            cur.execute(
                "DELETE FROM tracking_events WHERE tracking_number IN "
                "(SELECT tracking_number FROM orders WHERE user_id = %s)",
                [EVAL_USER],
            )
            cur.execute("DELETE FROM orders WHERE user_id = %s", [EVAL_USER])

            # 4. Reassign the 6 eval orders to eval_user
            for o in EVAL_ORDERS:
                cur.execute(
                    """INSERT INTO orders
                       (order_id, user_id, customer_name, status, carrier, tracking_number,
                        estimated_delivery, items, shipping_mode, order_region, order_country,
                        order_city, market, late_delivery_risk, benefit_per_order,
                        sales_per_customer, order_date)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (order_id) DO UPDATE SET user_id = EXCLUDED.user_id,
                           status = EXCLUDED.status, customer_name = EXCLUDED.customer_name""",
                    [
                        o["order_id"],
                        EVAL_USER,
                        o["customer_name"],
                        o["status"],
                        o["carrier"],
                        o["tracking_number"],
                        o["estimated_delivery"],
                        psycopg2.extras.Json(o["items"]),
                        o["shipping_mode"],
                        "South Asia",
                        "India",
                        o["order_city"],
                        "Pacific Asia",
                        0,
                        50.0,
                        500.0,
                        o["order_date"],
                    ],
                )

            # 5. Insert tracking events
            for tn, t in TRACKING_EVENTS.items():
                cur.execute(
                    """INSERT INTO tracking_events
                       (tracking_number, carrier, current_location, status, last_update,
                        estimated_delivery, events, days_for_shipping_real,
                        days_for_shipment_scheduled, delivery_status, shipping_date,
                        latitude, longitude)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (tracking_number) DO UPDATE SET
                           status = EXCLUDED.status, last_update = EXCLUDED.last_update""",
                    [
                        tn,
                        t["carrier"],
                        t["location"],
                        t["status"],
                        t["last_update"],
                        t["eta"],
                        psycopg2.extras.Json(t["events"]),
                        t["days_real"],
                        t["days_sched"],
                        t["delivery_status"],
                        t["ship_date"],
                        next((o["lat"] for o in EVAL_ORDERS if o["tracking_number"] == tn), 0.0),
                        next((o["lon"] for o in EVAL_ORDERS if o["tracking_number"] == tn), 0.0),
                    ],
                )

    print("✅ eval_user created")
    print(f"✅ {len(EVAL_ORDERS)} orders seeded: {[o['order_id'] for o in EVAL_ORDERS]}")
    print(f"✅ {len(TRACKING_EVENTS)} tracking events seeded")
    print("✅ Active sessions expired")
    print()
    print("Order summary:")
    for o in EVAL_ORDERS:
        print(f"  {o['order_id']} — {o['status']} — {o['carrier']} — {o['items']}")


if __name__ == "__main__":
    print("Seeding eval data...")
    seed()
    print("\nDone. Ready to run: python eval/run_eval.py")
