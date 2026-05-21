import sys
import os
import uuid
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta

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


USERS = [
    {"user_id": "user_001", "metadata": {"name": "John Doe",      "email": "john@example.com"}},
    {"user_id": "user_002", "metadata": {"name": "Jane Smith",     "email": "jane@example.com"}},
    {"user_id": "user_003", "metadata": {"name": "Alice Kumar",    "email": "alice@example.com"}},
    {"user_id": "user_004", "metadata": {"name": "Bob Sharma",     "email": "bob@example.com"}},
    {"user_id": "user_005", "metadata": {"name": "Priya Patel",    "email": "priya@example.com"}},
    {"user_id": "user_006", "metadata": {"name": "Rahul Verma",    "email": "rahul@example.com"}},
    {"user_id": "user_007", "metadata": {"name": "Anita Singh",    "email": "anita@example.com"}},
    {"user_id": "user_008", "metadata": {"name": "Vijay Reddy",    "email": "vijay@example.com"}},
    {"user_id": "user_009", "metadata": {"name": "Meena Nair",     "email": "meena@example.com"}},
    {"user_id": "user_010", "metadata": {"name": "Arjun Mehta",    "email": "arjun@example.com"}},
]

CONVERSATIONS = [
    {
        "user_id": "user_001",
        "messages": [
            {"role": "user",      "content": "Where is my order ORD001?",                          "agent_name": None},
            {"role": "assistant", "content": "Your order ORD001 is in transit with FedEx.",         "agent_name": "order_agent"},
            {"role": "user",      "content": "When will it arrive?",                               "agent_name": None},
            {"role": "assistant", "content": "It is expected to arrive by January 16th by 6 PM.",   "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_002",
        "messages": [
            {"role": "user",      "content": "Track my order ORD002",                              "agent_name": None},
            {"role": "assistant", "content": "Your order ORD002 has been delivered successfully.",  "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_003",
        "messages": [
            {"role": "user",      "content": "Where is order ORD003?",                             "agent_name": None},
            {"role": "assistant", "content": "Your order ORD003 is out for delivery with Bluedart.","agent_name": "order_agent"},
            {"role": "user",      "content": "What items are in this order?",                      "agent_name": None},
            {"role": "assistant", "content": "Your order contains: Headphones.",                   "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_004",
        "messages": [
            {"role": "user",      "content": "Is my order ORD004 dispatched?",                     "agent_name": None},
            {"role": "assistant", "content": "Your order ORD004 is currently pending dispatch.",    "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_005",
        "messages": [
            {"role": "user",      "content": "Why is my order ORD005 delayed?",                    "agent_name": None},
            {"role": "assistant", "content": "Your order ORD005 is delayed due to weather.",        "agent_name": "order_agent"},
            {"role": "user",      "content": "When will it reach me?",                             "agent_name": None},
            {"role": "assistant", "content": "Expected delivery is now January 20th.",              "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_006",
        "messages": [
            {"role": "user",      "content": "Check status of ORD006",                             "agent_name": None},
            {"role": "assistant", "content": "Order ORD006 is in transit via Ekart.",               "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_007",
        "messages": [
            {"role": "user",      "content": "Has ORD007 been delivered?",                         "agent_name": None},
            {"role": "assistant", "content": "Yes, ORD007 was delivered successfully.",             "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_008",
        "messages": [
            {"role": "user",      "content": "I want to return order ORD008",                      "agent_name": None},
            {"role": "assistant", "content": "Order ORD008 has already been returned to seller.",   "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_009",
        "messages": [
            {"role": "user",      "content": "Where is my order ORD009?",                          "agent_name": None},
            {"role": "assistant", "content": "Your order ORD009 is out for delivery today.",        "agent_name": "order_agent"},
            {"role": "user",      "content": "What is the tracking number?",                       "agent_name": None},
            {"role": "assistant", "content": "Your tracking number is BD100009 via Bluedart.",      "agent_name": "order_agent"},
        ]
    },
    {
        "user_id": "user_010",
        "messages": [
            {"role": "user",      "content": "Status of order ORD010 please",                      "agent_name": None},
            {"role": "assistant", "content": "Order ORD010 is in transit via DTDC.",                "agent_name": "order_agent"},
        ]
    },
]


def seed_users():
    with get_conn() as conn:
        with conn.cursor() as cur:
            for u in USERS:
                cur.execute(
                    "INSERT INTO users (user_id, created_at, metadata) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                    [u["user_id"], datetime.now(timezone.utc), psycopg2.extras.Json(u["metadata"])]
                )
    print(f"Seeded {len(USERS)} users.")


def seed_sessions_and_messages():
    with get_conn() as conn:
        with conn.cursor() as cur:
            for convo in CONVERSATIONS:
                user_id    = convo["user_id"]
                session_id = str(uuid.uuid4())

                # Create session
                cur.execute(
                    """INSERT INTO sessions
                       (session_id, user_id, created_at, last_active_at, is_active, agent_last_used)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (session_id) DO NOTHING""",
                    [session_id, user_id,
                     datetime.now(timezone.utc),
                     datetime.now(timezone.utc),
                     True, "order_agent"]
                )

                # Create messages for this session
                for i, msg in enumerate(convo["messages"]):
                    msg_time = datetime.now(timezone.utc) + timedelta(minutes=i)
                    cur.execute(
                        """INSERT INTO messages
                           (message_id, session_id, role, content, agent_name,
                            created_at, token_usage, mlflow_run_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [
                            str(uuid.uuid4()),
                            session_id,
                            msg["role"],
                            msg["content"],
                            msg["agent_name"],
                            msg_time,
                            psycopg2.extras.Json({"total_tokens": 20, "total_cost_usd": 0.000006}),
                            None,
                        ]
                    )

    print(f"Seeded {len(CONVERSATIONS)} sessions with messages.")


if __name__ == "__main__":
    print("Seeding users, sessions and messages...")
    seed_users()
    seed_sessions_and_messages()
    print("Done.")