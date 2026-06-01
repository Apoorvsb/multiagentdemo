"""Seed additional orders for apoorva.sb@sigmoidanalytics.com across 2025-2026."""
import json
import random
import psycopg2
import psycopg2.extras
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

USER_ID = "apoorva.sb@sigmoidanalytics.com"
CUSTOMER_NAME = "Apoorva S B"

CARRIERS = {
    "Xpressbees": ("XB20", "Mumbai Xpressbees Hub"),
    "FedEx":      ("FX20", "Chennai Gateway"),
    "Delhivery":  ("DL20", "Delhi NCR Facility"),
    "Shadowfax":  ("SF20", "Bangalore Hub"),
    "Ekart":      ("EK20", "Hyderabad Facility"),
    "BlueDart":   ("BD20", "Pune Gateway"),
    "DTDC":       ("DT20", "Kolkata Depot"),
}

CITIES = [
    ("Bangalore", 12.9716, 77.5946),
    ("Mumbai",    19.0760, 72.8777),
    ("Delhi",     28.7041, 77.1025),
    ("Hyderabad", 17.3850, 78.4867),
    ("Chennai",   13.0827, 80.2707),
    ("Pune",      18.5204, 73.8567),
    ("Kolkata",   22.5726, 88.3639),
    ("Ahmedabad", 23.0225, 72.5714),
    ("Jaipur",    26.9124, 75.7873),
    ("Surat",     21.1702, 72.8311),
    ("Lucknow",   26.8467, 80.9462),
    ("Indore",    22.7196, 75.8577),
]

PRODUCTS = [
    ["Laptop"], ["Smartphone"], ["Wireless Earbuds"], ["Mechanical Keyboard"],
    ["Gaming Mouse"], ["USB Hub"], ["SSD"], ["RAM"],
    ["Monitor"], ["Webcam"], ["Desk Lamp"], ["Notebook"],
    ["T-Shirt"], ["Jeans"], ["Running Shoes"], ["Backpack"],
    ["Water Bottle"], ["Coffee Mug"], ["Yoga Mat"], ["Resistance Bands"],
    ["Headphones"], ["Smart Watch"], ["Tablet"], ["Power Bank"],
    ["Charger"], ["Cable"], ["Router"], ["Pendrive"],
    ["Sunglasses"], ["Wallet"], ["Perfume"], ["Books"],
    ["Laptop Stand"], ["Mouse Pad"], ["Desk Organizer"], ["Sticky Notes"],
    ["Bluetooth Speaker"], ["Action Camera"], ["Electric Kettle"], ["Air Fryer"],
    ["Laptop", "Mouse"], ["Keyboard", "Mouse"], ["RAM", "SSD"], ["Earbuds", "Case"],
]

SHIPPING_MODES = ["Standard Class", "Standard Class", "Standard Class", "Second Class", "First Class", "Express"]

STATUSES_PAST    = ["DELIVERED", "DELIVERED", "DELIVERED", "RETURNED", "DELIVERED"]
STATUSES_RECENT  = ["DELIVERED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "PENDING", "DELAYED"]
STATUSES_JUNE26  = ["PENDING", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "DELAYED", "PENDING"]


def make_events(order_date, status, shipping_date):
    evts = [
        {"time": f"{order_date}T10:00:00Z",    "status": "Order placed"},
        {"time": f"{shipping_date}T08:00:00Z", "status": "Picked up from seller"},
        {"time": f"{shipping_date}T20:00:00Z", "status": "In transit"},
    ]
    if status in ("OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"):
        evts.append({"time": f"{shipping_date}T22:00:00Z", "status": "Reached local facility"})
        evts.append({"time": f"{shipping_date}T23:00:00Z", "status": "Out for delivery"})
    if status == "DELIVERED":
        evts.append({"time": f"{shipping_date}T23:30:00Z", "status": "Delivered"})
    if status == "RETURNED":
        evts.append({"time": f"{shipping_date}T23:30:00Z", "status": "Delivered"})
        evts.append({"time": f"{shipping_date}T23:45:00Z", "status": "Return initiated"})
    if status == "DELAYED":
        evts.append({"time": f"{shipping_date}T23:00:00Z", "status": "Shipment delayed"})
    return evts


def add_days(date_str, days):
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def build_orders():
    orders = []
    seq = 2001

    # 2025 — ~45 orders spread across all 12 months
    months_2025 = [
        ("2025-01", 4), ("2025-02", 3), ("2025-03", 4), ("2025-04", 3),
        ("2025-05", 4), ("2025-06", 4), ("2025-07", 3), ("2025-08", 4),
        ("2025-09", 3), ("2025-10", 5), ("2025-11", 5), ("2025-12", 5),
    ]
    for ym, count in months_2025:
        for i in range(count):
            day = random.randint(1, 28)
            order_date = f"{ym}-{day:02d}"
            orders.append((seq, order_date, STATUSES_PAST[seq % len(STATUSES_PAST)]))
            seq += 1

    # 2026 Jan–May — ~25 orders
    months_2026_early = [
        ("2026-01", 5), ("2026-02", 5), ("2026-03", 5), ("2026-04", 5), ("2026-05", 5),
    ]
    for ym, count in months_2026_early:
        for i in range(count):
            day = random.randint(1, 28)
            order_date = f"{ym}-{day:02d}"
            orders.append((seq, order_date, STATUSES_RECENT[seq % len(STATUSES_RECENT)]))
            seq += 1

    # June 2026 — 20 orders, dense
    for day in [1,2,3,4,5,7,8,9,10,11,13,14,15,17,18,19,20,21,24,25]:
        order_date = f"2026-06-{day:02d}"
        orders.append((seq, order_date, STATUSES_JUNE26[seq % len(STATUSES_JUNE26)]))
        seq += 1

    return orders


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


def seed():
    random.seed(42)
    orders = build_orders()
    carrier_names = list(CARRIERS.keys())

    with get_conn() as conn:
        with conn.cursor() as cur:
            for seq, order_date, status in orders:
                carrier_name = carrier_names[seq % len(carrier_names)]
                prefix, location = CARRIERS[carrier_name]
                tracking_number = f"{prefix}{seq}"
                ship_days = random.randint(1, 3)
                deliver_days = random.randint(4, 8)
                shipping_date = add_days(order_date, ship_days)
                estimated_delivery = add_days(order_date, deliver_days)
                city, lat, lon = CITIES[seq % len(CITIES)]
                items = PRODUCTS[seq % len(PRODUCTS)]
                shipping_mode = SHIPPING_MODES[seq % len(SHIPPING_MODES)]
                late_risk = 1 if status in ("DELAYED", "RETURNED") else 0
                sales = round(random.uniform(200, 5000), 2)
                benefit = round(random.uniform(20, 500), 2)

                cur.execute("""
                    INSERT INTO orders
                        (order_id, user_id, customer_name, status, carrier, tracking_number,
                         estimated_delivery, items, shipping_mode, order_region,
                         order_country, order_city, market, late_delivery_risk,
                         benefit_per_order, sales_per_customer, order_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (order_id) DO UPDATE SET
                        user_id=EXCLUDED.user_id, status=EXCLUDED.status
                """, [
                    f"ORD{seq}", USER_ID, CUSTOMER_NAME, status, carrier_name,
                    tracking_number, estimated_delivery,
                    psycopg2.extras.Json(items), shipping_mode,
                    "South Asia", "India", city, "Pacific Asia",
                    late_risk, benefit, sales, order_date,
                ])

                events = make_events(order_date, status, shipping_date)
                actual_days = deliver_days + random.randint(-1, 3)
                sched_days = deliver_days
                delivery_status = "Late delivery" if actual_days > sched_days else "Advance shipping"

                cur.execute("""
                    INSERT INTO tracking_events
                        (tracking_number, carrier, current_location, status,
                         last_update, estimated_delivery, events,
                         days_for_shipping_real, days_for_shipment_scheduled,
                         delivery_status, shipping_date, latitude, longitude)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tracking_number) DO NOTHING
                """, [
                    tracking_number, carrier_name, location, status,
                    f"{estimated_delivery}T00:00:00Z",
                    f"{estimated_delivery}T00:00:00Z",
                    psycopg2.extras.Json(events),
                    actual_days, sched_days, delivery_status,
                    shipping_date, lat, lon,
                ])

    print(f"Inserted {len(orders)} orders for {USER_ID}")
    print(f"  2025: {sum(1 for _, d, _ in orders if d.startswith('2025'))} orders")
    print(f"  2026 Jan-May: {sum(1 for _, d, _ in orders if d.startswith('2026') and not d.startswith('2026-06'))} orders")
    print(f"  2026 June: {sum(1 for _, d, _ in orders if d.startswith('2026-06'))} orders")


if __name__ == "__main__":
    seed()
