import uuid
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from typing import Optional
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
    CREATE TABLE IF NOT EXISTS users (
        user_id    TEXT PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        metadata   JSONB NOT NULL DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_id      TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL REFERENCES users(user_id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        agent_last_used TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        message_id    TEXT PRIMARY KEY,
        session_id    TEXT NOT NULL REFERENCES sessions(session_id),
        role          TEXT NOT NULL CHECK (role IN ('user','assistant')),
        content       TEXT NOT NULL,
        agent_name    TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        token_usage   JSONB NOT NULL DEFAULT '{}',
        mlflow_run_id TEXT
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def get_or_create_user(user_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE user_id = %s", [user_id])
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO users (user_id, created_at, metadata) VALUES (%s, %s, %s)",
                    [user_id, datetime.now(timezone.utc), psycopg2.extras.Json({})]
                )


def get_or_create_session(session_id: Optional[str], user_id: str) -> str:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if session_id:
                cur.execute("SELECT * FROM sessions WHERE session_id = %s", [session_id])
                session = cur.fetchone()
                if not session:
                    raise ValueError("Session not found.")
                last_active = session["last_active_at"]
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=config.SESSION_EXPIRY_MINUTES)
                if last_active < cutoff:
                    cur.execute("UPDATE sessions SET is_active = false WHERE session_id = %s", [session_id])
                    raise ValueError("Session expired. Please start a new conversation.")
                cur.execute(
                    "UPDATE sessions SET last_active_at = %s WHERE session_id = %s",
                    [datetime.now(timezone.utc), session_id]
                )
                return session_id
            # else:
            #     new_id = str(uuid.uuid4())
            #     cur.execute(
            #         "INSERT INTO sessions (session_id, user_id, created_at, last_active_at, is_active) VALUES (%s, %s, %s, %s, %s)",
            #         [new_id, user_id, datetime.now(timezone.utc), datetime.now(timezone.utc), True]
            #     )
            #     return new_id
            else:
                # Check if user has an existing active session within expiry window
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=config.SESSION_EXPIRY_MINUTES)
                cur.execute(
                    """SELECT session_id FROM sessions
                       WHERE user_id = %s AND is_active = true
                       AND last_active_at > %s
                       ORDER BY last_active_at DESC LIMIT 1""",
                    [user_id, cutoff]
                )
                existing = cur.fetchone()
                if existing:
                    # Reuse existing active session
                    cur.execute(
                        "UPDATE sessions SET last_active_at = %s WHERE session_id = %s",
                        [datetime.now(timezone.utc), existing["session_id"]]
                    )
                    return existing["session_id"]

                # No active session — create new one
                new_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO sessions (session_id, user_id, created_at, last_active_at, is_active) VALUES (%s, %s, %s, %s, %s)",
                    [new_id, user_id, datetime.now(timezone.utc), datetime.now(timezone.utc), True]
                )
                return new_id


def update_session_agent(session_id: str, agent_name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET agent_last_used = %s WHERE session_id = %s",
                [agent_name, session_id]
            )


def load_conversation_history(session_id: str) -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT role, content FROM messages WHERE session_id = %s ORDER BY created_at ASC",
                [session_id]
            )
            return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]


def save_message(session_id, role, content, agent_name=None, token_usage=None, mlflow_run_id=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO messages
                   (message_id, session_id, role, content, agent_name, created_at, token_usage, mlflow_run_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    str(uuid.uuid4()), session_id, role, content, agent_name,
                    datetime.now(timezone.utc),
                    psycopg2.extras.Json(token_usage or {}),
                    mlflow_run_id,
                ]
            )