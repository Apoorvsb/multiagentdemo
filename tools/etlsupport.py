import csv
import sys
import os
import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


# ─────────────────────────────────────────────
# CREATE TABLES
# ─────────────────────────────────────────────

def create_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS policies (
        policy_id          TEXT PRIMARY KEY,
        issue_type         TEXT NOT NULL,
        category           TEXT,
        policy_text        TEXT NOT NULL,
        refund_eligible    BOOLEAN DEFAULT FALSE,
        replacement_eligible BOOLEAN DEFAULT FALSE,
        return_window_days INTEGER DEFAULT 7,
        severity_default   TEXT DEFAULT 'LOW',
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id          TEXT PRIMARY KEY,
        user_id            TEXT REFERENCES users(user_id),
        session_id         TEXT REFERENCES sessions(session_id),
        customer_name      TEXT,
        customer_email     TEXT,
        product_purchased  TEXT,
        issue_type         TEXT,
        ticket_subject     TEXT,
        description        TEXT,
        status             TEXT DEFAULT 'Open',
        resolution         TEXT,
        priority           TEXT DEFAULT 'Medium',
        channel            TEXT,
        severity           TEXT DEFAULT 'LOW',
        first_response_time TEXT,
        time_to_resolution  TEXT,
        satisfaction_rating TEXT,
        date_of_purchase   TEXT,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Tables created — policies and tickets.")


# ─────────────────────────────────────────────
# HARDCODED POLICIES
# These are company-defined business rules
# One policy per issue type
# ─────────────────────────────────────────────

POLICIES = [
    {
        "policy_id":           "POL001",
        "issue_type":          "damaged_goods",
        "category":            "Physical Damage",
        "policy_text":         "If the product arrives damaged, the customer is eligible for a full refund or replacement within 7 days of delivery. Customer must provide photo evidence of the damage. Refund will be processed within 5-7 business days.",
        "refund_eligible":     True,
        "replacement_eligible":True,
        "return_window_days":  7,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL002",
        "issue_type":          "wrong_item",
        "category":            "Incorrect Order",
        "policy_text":         "If the customer receives a wrong item, they are eligible for a full replacement or refund within 14 days. The wrong item must be returned in original condition. Shipping cost for return is covered by the company.",
        "refund_eligible":     True,
        "replacement_eligible":True,
        "return_window_days":  14,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL003",
        "issue_type":          "missing_item",
        "category":            "Missing Package",
        "policy_text":         "If the order is marked delivered but the customer has not received it, a full refund is issued after 48 hours of investigation. Customer must confirm the delivery address was correct. No return required.",
        "refund_eligible":     True,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL004",
        "issue_type":          "refund_request",
        "category":            "Refund",
        "policy_text":         "Refund requests are accepted within 30 days of purchase for unopened products. Opened products are eligible for refund only if defective. Refund is processed within 7-10 business days to the original payment method.",
        "refund_eligible":     True,
        "replacement_eligible":False,
        "return_window_days":  30,
        "severity_default":    "MEDIUM",
    },
    {
        "policy_id":           "POL005",
        "issue_type":          "technical_issue",
        "category":            "Technical Support",
        "policy_text":         "Technical issues are handled by the support team within 24 hours. If the issue cannot be resolved remotely, a replacement is offered within the warranty period. Warranty period is 1 year from date of purchase.",
        "refund_eligible":     False,
        "replacement_eligible":True,
        "return_window_days":  365,
        "severity_default":    "MEDIUM",
    },
    {
        "policy_id":           "POL006",
        "issue_type":          "billing_inquiry",
        "category":            "Billing",
        "policy_text":         "Billing disputes must be raised within 60 days of the transaction. Duplicate charges are refunded within 3-5 business days. Incorrect charges are investigated within 24 hours and resolved within 7 business days.",
        "refund_eligible":     True,
        "replacement_eligible":False,
        "return_window_days":  60,
        "severity_default":    "MEDIUM",
    },
    {
        "policy_id":           "POL007",
        "issue_type":          "cancellation_request",
        "category":            "Order Cancellation",
        "policy_text":         "Orders can be cancelled before they are shipped. Once shipped, cancellation is not possible and the return policy applies. Full refund is issued for cancelled orders within 3-5 business days.",
        "refund_eligible":     True,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "LOW",
    },
    {
        "policy_id":           "POL008",
        "issue_type":          "product_inquiry",
        "category":            "Product Information",
        "policy_text":         "Product inquiries are answered within 24 hours by the support team. Detailed product specifications and compatibility information are available on the product page. For bulk orders contact enterprise support.",
        "refund_eligible":     False,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "LOW",
    },
    {
        "policy_id":           "POL009",
        "issue_type":          "delayed_delivery",
        "category":            "Delivery Delay",
        "policy_text":         "If delivery is delayed beyond the estimated date by more than 7 days, the customer is eligible for a partial refund of shipping charges. If delayed by more than 14 days, a full refund or reshipment is offered.",
        "refund_eligible":     True,
        "replacement_eligible":True,
        "return_window_days":  14,
        "severity_default":    "MEDIUM",
    },
    {
        "policy_id":           "POL010",
        "issue_type":          "warranty_claim",
        "category":            "Warranty",
        "policy_text":         "Products are covered under a 1-year manufacturer warranty from date of purchase. Warranty covers manufacturing defects only. Physical damage, water damage, and unauthorised modifications are not covered.",
        "refund_eligible":     False,
        "replacement_eligible":True,
        "return_window_days":  365,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL011",
        "issue_type":          "return_request",
        "category":            "Product Return",
        "policy_text":         "Products can be returned within 30 days of delivery in original packaging. The product must be unused and in resalable condition. Return shipping is free for defective products. Customer pays return shipping for change of mind returns.",
        "refund_eligible":     True,
        "replacement_eligible":False,
        "return_window_days":  30,
        "severity_default":    "LOW",
    },
    {
        "policy_id":           "POL012",
        "issue_type":          "account_issue",
        "category":            "Account",
        "policy_text":         "Account issues including login problems, password resets, and profile updates are resolved within 24 hours. For security concerns related to unauthorized access, the account is immediately locked and the customer is contacted.",
        "refund_eligible":     False,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL013",
        "issue_type":          "payment_failed",
        "category":            "Payment",
        "policy_text":         "Failed payments are automatically retried 3 times. If payment continues to fail, the customer is notified to update payment details. No charges are made for failed transactions. Order is held for 48 hours before cancellation.",
        "refund_eligible":     False,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "MEDIUM",
    },
    {
        "policy_id":           "POL014",
        "issue_type":          "product_not_as_described",
        "category":            "Product Quality",
        "policy_text":         "If the product received does not match the description on the website, the customer is eligible for a full refund or replacement within 14 days. Photo evidence is required. No return needed if the product value is below 500 rupees.",
        "refund_eligible":     True,
        "replacement_eligible":True,
        "return_window_days":  14,
        "severity_default":    "HIGH",
    },
    {
        "policy_id":           "POL015",
        "issue_type":          "general_complaint",
        "category":            "General",
        "policy_text":         "General complaints are reviewed within 48 hours. A customer service representative will contact the customer to understand the issue and offer an appropriate resolution based on the specific circumstances.",
        "refund_eligible":     False,
        "replacement_eligible":False,
        "return_window_days":  0,
        "severity_default":    "LOW",
    },
]

# Map CSV ticket types to our policy issue types
TICKET_TYPE_MAP = {
    "Technical issue":      "technical_issue",
    "Billing inquiry":      "billing_inquiry",
    "Refund request":       "refund_request",
    "Product inquiry":      "product_inquiry",
    "Cancellation request": "cancellation_request",
}

PRIORITY_MAP = {
    "Critical": "PRIORITY_1",
    "High":     "PRIORITY_2",
    "Medium":   "PRIORITY_3",
    "Low":      "PRIORITY_4",
}

SEVERITY_MAP = {
    "Critical": "HIGH",
    "High":     "HIGH",
    "Medium":   "MEDIUM",
    "Low":      "LOW",
}


# ─────────────────────────────────────────────
# LOAD POLICIES
# ─────────────────────────────────────────────

def load_policies():
    with get_conn() as conn:
        with conn.cursor() as cur:
            for p in POLICIES:
                cur.execute(
                    """
                    INSERT INTO policies
                        (policy_id, issue_type, category, policy_text,
                         refund_eligible, replacement_eligible,
                         return_window_days, severity_default)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (policy_id) DO NOTHING
                    """,
                    [
                        p["policy_id"],
                        p["issue_type"],
                        p["category"],
                        p["policy_text"],
                        p["refund_eligible"],
                        p["replacement_eligible"],
                        p["return_window_days"],
                        p["severity_default"],
                    ]
                )
    print(f"Loaded {len(POLICIES)} policies.")


# ─────────────────────────────────────────────
# LOAD TICKETS FROM CSV
# ─────────────────────────────────────────────

def load_tickets(filepath, limit=2000):
    if not os.path.exists(filepath):
        print(f"ERROR: {filepath} not found.")
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows   = list(reader)[:limit]

    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                ticket_id   = f"TKT{row['Ticket ID'].strip().zfill(6)}"
                issue_type  = TICKET_TYPE_MAP.get(
                    row.get("Ticket Type", "").strip(),
                    "general_complaint"
                )
                priority_raw = row.get("Ticket Priority", "Medium").strip()
                priority     = PRIORITY_MAP.get(priority_raw, "PRIORITY_3")
                severity     = SEVERITY_MAP.get(priority_raw, "MEDIUM")
                status       = row.get("Ticket Status", "Open").strip()
                resolution   = row.get("Resolution", "").strip() or None

                try:
                    cur.execute(
                        """
                        INSERT INTO tickets
                            (ticket_id, user_id, session_id,
                             customer_name, customer_email,
                             product_purchased, issue_type,
                             ticket_subject, description,
                             status, resolution, priority,
                             channel, severity,
                             first_response_time, time_to_resolution,
                             satisfaction_rating, date_of_purchase)
                        VALUES
                            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticket_id) DO NOTHING
                        """,
                        [
                            ticket_id,
                            None,       # user_id — null for seeded data
                            None,       # session_id — null for seeded data
                            row.get("Customer Name",   "").strip(),
                            row.get("Customer Email",  "").strip(),
                            row.get("Product Purchased","").strip(),
                            issue_type,
                            row.get("Ticket Subject",  "").strip(),
                            row.get("Ticket Description","").strip()[:1000],
                            status,
                            resolution,
                            priority,
                            row.get("Ticket Channel",  "").strip(),
                            severity,
                            row.get("First Response Time","").strip() or None,
                            row.get("Time to Resolution","").strip() or None,
                            row.get("Customer Satisfaction Rating","").strip() or None,
                            row.get("Date of Purchase","").strip() or None,
                        ]
                    )
                    inserted += 1
                except Exception as e:
                    print(f"Ticket error {ticket_id}: {e}")

    print(f"Loaded {inserted} tickets from CSV.")
    return inserted


# ─────────────────────────────────────────────
# VERIFY
# ─────────────────────────────────────────────

def verify():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM policies")
            p_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM tickets")
            t_count = cur.fetchone()[0]

            cur.execute(
                "SELECT issue_type, COUNT(*) FROM tickets "
                "GROUP BY issue_type ORDER BY COUNT(*) DESC"
            )
            issue_counts = cur.fetchall()

            cur.execute(
                "SELECT severity_default, COUNT(*) FROM policies "
                "GROUP BY severity_default"
            )
            severity_counts = cur.fetchall()

    print(f"\n=== Verification ===")
    print(f"policies table → {p_count} rows")
    print(f"tickets  table → {t_count} rows")

    print(f"\nTickets by issue type:")
    for issue, count in issue_counts:
        print(f"  {issue:<30} {count}")

    print(f"\nPolicies by severity:")
    for sev, count in severity_counts:
        print(f"  {sev:<10} {count}")


# ─────────────────────────────────────────────
# MAIN — ETL PIPELINE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    filepath = os.path.join(
        os.path.dirname(__file__),
        "customer_support_tickets.csv"
    )

    print("=" * 55)
    print("ETL Pipeline — Agent 3: Support & Resolution")
    print("=" * 55)

    # Step 1 — Create tables
    print("\n[1/4] Creating tables...")
    create_tables()

    # Step 2 — Load hardcoded policies
    print("\n[2/4] Loading policies...")
    load_policies()

    # Step 3 — Load tickets from CSV
    print("\n[3/4] Loading tickets from CSV (first 2000 rows)...")
    load_tickets(filepath, limit=2000)

    # Step 4 — Verify
    print("\n[4/4] Verifying...")
    verify()

    print("\nETL pipeline completed successfully.")