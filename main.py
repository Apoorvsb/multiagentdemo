import uuid
import time
import asyncio
import logging
import mlflow
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from config import config
from state import empty_state
from logger import get_log
from database import (
    create_tables,
    get_or_create_user,
    get_or_create_session,
    load_conversation_history,
    save_message,
    update_session_agent,
)
from mlflow_helpers import setup_mlflow
from pipeline import pipeline
from opentelemetry import context as otel_context
from opentelemetry.propagate import inject

# ── Sliding window memory ─────────────────────────────────────────
WINDOW_SIZE = 4  # recent messages kept verbatim (2 user+assistant exchanges)


def build_sliding_window(history: list) -> tuple[str, list]:
    """
    Split session history into a compact summary of older messages and a
    verbatim window of the most recent ones.  No LLM — summary is built
    deterministically so it costs zero tokens to produce.
    """
    if len(history) <= WINDOW_SIZE:
        return "", history

    older = history[:-WINDOW_SIZE]
    recent = history[-WINDOW_SIZE:]

    # Summarise at most the last 6 older messages so the summary stays
    # compact (~80-120 tokens) regardless of session length.
    sample = older[-6:]
    parts = []
    for m in sample:
        role = m.get("role", "?")
        content = (m.get("content") or "").replace("\n", " ").strip()
        snippet = content[:70] + ("…" if len(content) > 70 else "")
        parts.append(f"[{role}]: {snippet}")

    summary = "Earlier in this session — " + " → ".join(parts)
    return summary, recent


# ── Prometheus metrics ─────────────────────────────────────
REQUEST_COUNT = Counter("multiagent_requests_total", "Total requests", ["endpoint", "agent", "status"])
REQUEST_LATENCY = Histogram("multiagent_request_latency_seconds", "Request latency in seconds", ["agent"])
TOKEN_USAGE = Counter("multiagent_tokens_total", "Total tokens used", ["agent"])
ERROR_COUNT = Counter("multiagent_errors_total", "Total errors", ["agent"])

# ── Suppress only the span warning, not all tracing ───────
logging.getLogger("mlflow.entities.span").setLevel(logging.CRITICAL)


# ── Traced pipeline wrapper ────────────────────────────────
# @mlflow.trace(name="multi_agent_pipeline", span_type="CHAIN")
# def run_pipeline(state):
#     return pipeline.invoke(state)
def run_pipeline(state, carrier=None):
    from opentelemetry.propagate import extract

    if carrier:
        ctx = extract(carrier)
        token = otel_context.attach(ctx)
        try:
            return pipeline.invoke(state)
        finally:
            otel_context.detach(token)
    return pipeline.invoke(state)


import logging

logging.getLogger("mlflow.entities.span").setLevel(logging.CRITICAL)
logging.getLogger("mlflow.tracing").setLevel(logging.CRITICAL)
# ═══════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_mlflow()
    create_tables()
    yield


app = FastAPI(title="Multi-Agent App", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════
# DB HELPERS
# ═══════════════════════════════════════════════════════


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


def get_session_row(session_id: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM sessions WHERE session_id = %s", [session_id])
            row = cur.fetchone()
            return dict(row) if row else None


def update_user_metadata(user_id: str, metadata: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET metadata = %s WHERE user_id = %s", [psycopg2.extras.Json(metadata), user_id])


def user_exists(user_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE user_id = %s", [user_id])
            return cur.fetchone() is not None


# ═══════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════


class RegisterRequest(BaseModel):
    name: str
    email: str


class LoginRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: Optional[str]
    tokens_used: int
    cost_usd: float


# ═══════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


ALLOWED_DOMAIN = "sigmoidanalytics.com"


@app.post("/register")
async def register(body: RegisterRequest):
    user_id = body.email
    is_guest = not user_id.lower().endswith("@" + ALLOWED_DOMAIN)

    # Guest users get a @guest.com user_id so agents can identify and restrict them
    if is_guest:
        user_id = body.email.split("@")[0] + "@guest.com"

    if user_exists(user_id):
        session_id = get_or_create_session(None, user_id)
        return {
            "user_id": user_id,
            "session_id": session_id,
            "name": body.name,
            "message": "User already exists. Logged in successfully.",
            "existing_user": True,
            "is_guest": is_guest,
        }
    get_or_create_user(user_id)
    update_user_metadata(user_id, {"name": body.name, "email": body.email, "is_guest": is_guest})
    session_id = get_or_create_session(None, user_id)

    return {
        "user_id": user_id,
        "session_id": session_id,
        "name": body.name,
        "message": "Registration successful." if not is_guest else "Guest account created. You can browse products only.",
        "existing_user": False,
        "is_guest": is_guest,
    }


# ── Admin: manually seed demo orders for any user ────────────────
class SeedOrdersRequest(BaseModel):
    user_id: str
    count: Optional[int] = 10


@app.post("/admin/seed-orders")
async def seed_orders(body: SeedOrdersRequest):
    import random
    import string
    import json as _json
    from database import get_conn
    from datetime import date, timedelta

    if not user_exists(body.user_id):
        raise HTTPException(status_code=404, detail=f"User '{body.user_id}' not found. Register first.")

    TEMPLATES = [
        {
            "status": "DELIVERED",
            "carrier": "FedEx",
            "items": ["Wireless Mouse"],
            "price": 499,
            "days_ago": 20,
            "eta_offset": -10,
            "mode": "Standard Class",
            "risk": 0,
        },
        {
            "status": "DELIVERED",
            "carrier": "Ekart",
            "items": ["Laptop Stand", "Laptop Bag"],
            "price": 1899,
            "days_ago": 45,
            "eta_offset": -30,
            "mode": "First Class",
            "risk": 0,
        },
        {
            "status": "DELIVERED",
            "carrier": "Delhivery",
            "items": ["Wireless Earbuds"],
            "price": 3499,
            "days_ago": 30,
            "eta_offset": -20,
            "mode": "Express",
            "risk": 0,
        },
        {
            "status": "DELIVERED",
            "carrier": "Bluedart",
            "items": ["Smart Watch"],
            "price": 8999,
            "days_ago": 60,
            "eta_offset": -45,
            "mode": "First Class",
            "risk": 0,
        },
        {
            "status": "DELIVERED",
            "carrier": "FedEx",
            "items": ["Noise Cancelling Headphones"],
            "price": 12999,
            "days_ago": 25,
            "eta_offset": -15,
            "mode": "Express",
            "risk": 0,
        },
        {
            "status": "IN_TRANSIT",
            "carrier": "Delhivery",
            "items": ["Mechanical Keyboard", "Mousepad"],
            "price": 2499,
            "days_ago": 5,
            "eta_offset": 3,
            "mode": "Express",
            "risk": 0,
        },
        {
            "status": "IN_TRANSIT",
            "carrier": "FedEx",
            "items": ["Gaming Monitor"],
            "price": 18999,
            "days_ago": 4,
            "eta_offset": 5,
            "mode": "First Class",
            "risk": 0,
        },
        {
            "status": "PENDING",
            "carrier": "Bluedart",
            "items": ["USB Hub", "HDMI Cable"],
            "price": 599,
            "days_ago": 2,
            "eta_offset": 7,
            "mode": "Standard Class",
            "risk": 0,
        },
        {
            "status": "PENDING",
            "carrier": "Delhivery",
            "items": ["Webcam"],
            "price": 1999,
            "days_ago": 1,
            "eta_offset": 8,
            "mode": "Standard Class",
            "risk": 0,
        },
        {
            "status": "OUT_FOR_DELIVERY",
            "carrier": "Ekart",
            "items": ["Mechanical Keyboard"],
            "price": 4999,
            "days_ago": 7,
            "eta_offset": 0,
            "mode": "Express",
            "risk": 0,
        },
        {
            "status": "DELAYED",
            "carrier": "FedEx",
            "items": ["Webcam"],
            "price": 1999,
            "days_ago": 10,
            "eta_offset": -1,
            "mode": "Express",
            "risk": 1,
        },
        {
            "status": "RETURNED",
            "carrier": "Delhivery",
            "items": ["Defective Charger"],
            "price": 299,
            "days_ago": 40,
            "eta_offset": -25,
            "mode": "Standard Class",
            "risk": 0,
        },
    ]

    today = date.today()
    templates = TEMPLATES[: body.count] if body.count <= len(TEMPLATES) else TEMPLATES

    created = []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for t in templates:
                    order_id = "ORD" + "".join(random.choices(string.digits, k=6))
                    cur.execute(
                        """
                        INSERT INTO orders (
                            order_id, user_id, status, carrier, items,
                            sales_per_customer, estimated_delivery, order_date,
                            shipping_mode, late_delivery_risk
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (order_id) DO NOTHING
                    """,
                        [
                            order_id,
                            body.user_id,
                            t["status"],
                            t["carrier"],
                            _json.dumps(t["items"]),
                            t["price"],
                            str(today + timedelta(days=t["eta_offset"])),
                            str(today - timedelta(days=t["days_ago"])),
                            t["mode"],
                            t["risk"],
                        ],
                    )
                    tracking_number = t["carrier"][:2].upper() + "".join(random.choices(string.digits, k=8))
                    cur.execute(
                        """
                        UPDATE orders SET tracking_number = %s WHERE order_id = %s
                    """,
                        [tracking_number, order_id],
                    )
                    events = [
                        {"time": str(today - timedelta(days=t["days_ago"])) + "T09:00:00Z", "status": "Order placed"},
                        {
                            "time": str(today - timedelta(days=t["days_ago"] - 1)) + "T14:00:00Z",
                            "status": "Picked up from seller",
                        },
                    ]
                    if t["status"] not in ("PENDING",):
                        events.append(
                            {
                                "time": str(today - timedelta(days=max(t["days_ago"] - 2, 0))) + "T06:00:00Z",
                                "status": "In transit",
                            }
                        )
                    if t["status"] in ("OUT_FOR_DELIVERY", "DELIVERED"):
                        events.append(
                            {
                                "time": str(today + timedelta(days=t["eta_offset"])) + "T08:00:00Z",
                                "status": "Out for delivery",
                            }
                        )
                    if t["status"] == "DELIVERED":
                        events.append(
                            {"time": str(today + timedelta(days=t["eta_offset"])) + "T15:00:00Z", "status": "Delivered"}
                        )
                    if t["status"] == "DELAYED":
                        events.append(
                            {"time": str(today - timedelta(days=1)) + "T10:00:00Z", "status": "Delivery delayed"}
                        )
                    if t["status"] == "RETURNED":
                        events.append(
                            {
                                "time": str(today + timedelta(days=t["eta_offset"])) + "T11:00:00Z",
                                "status": "Return initiated",
                            }
                        )
                    cur.execute(
                        """
                        INSERT INTO tracking_events
                            (tracking_number, carrier, current_location, status,
                             last_update, estimated_delivery, events)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (tracking_number) DO NOTHING
                    """,
                        [
                            tracking_number,
                            t["carrier"],
                            t["carrier"] + " Hub",
                            t["status"],
                            str(today) + "T00:00:00Z",
                            str(today + timedelta(days=t["eta_offset"])) + "T00:00:00Z",
                            _json.dumps(events),
                        ],
                    )
                    created.append(
                        {
                            "order_id": order_id,
                            "tracking_number": tracking_number,
                            "status": t["status"],
                            "items": t["items"],
                        }
                    )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed failed: {e}")

    return {
        "user_id": body.user_id,
        "orders_created": len(created),
        "orders": created,
        "message": f"Successfully seeded {len(created)} demo orders for {body.user_id}.",
    }


@app.post("/login")
async def login(body: LoginRequest):
    if not user_exists(body.user_id):
        raise HTTPException(
            status_code=404,
            detail={"error": "User not found.", "action": "Please sign up first.", "signup_url": "/register"},
        )

    session_id = get_or_create_session(None, body.user_id)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT role, content, agent_name
                FROM messages
                WHERE session_id = %s
                ORDER BY created_at ASC
                LIMIT 20""",
                [session_id],
            )
            messages = [dict(r) for r in cur.fetchall()]  # ← must be inside with block

    return {
        "user_id": body.user_id,
        "session_id": session_id,
        "message": "Login successful.",
        "next_step": "Use session_id in X-Session-ID header for /chat.",
        "messages": messages,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_session_id: Optional[str] = Header(None),
):
    if not x_session_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "You are not logged in.",
                "message": "Please sign up or log in to continue.",
                "signup_url": "/register",
                "login_url": "/login",
            },
        )

    request_id = str(uuid.uuid4())
    log = get_log(request_id)
    start = time.time()

    # ── Load session ──────────────────────────────────────────────
    session_row = get_session_row(x_session_id)
    if not session_row:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Session not found.",
                "message": "Your session is invalid. Please log in again.",
                "login_url": "/login",
            },
        )

    user_id = session_row["user_id"]
    log.info(f"Request received | user_id={user_id} | input='{body.message[:60]}'")

    # ── Check session expiry ──────────────────────────────────────
    try:
        session_id = get_or_create_session(x_session_id, user_id)
    except ValueError as e:
        log.warning(f"Session expired: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Session expired.",
                "message": "Your session has expired. Please log in again.",
                "login_url": "/login",
            },
        )

    # ── Load history & apply sliding window ──────────────────────
    history = load_conversation_history(session_id)
    conv_summary, recent_messages = build_sliding_window(history)
    log.info(
        f"Session loaded | session_id={session_id} | "
        f"total={len(history)} | window={len(recent_messages)} | "
        f"summarised={len(history) - len(recent_messages)}"
    )

    # ── Save user message ─────────────────────────────────────────
    save_message(session_id=session_id, role="user", content=body.message)

    # ── Build state ───────────────────────────────────────────────
    state = empty_state(
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        messages=recent_messages,
        current_input=body.message,
    )
    state["conversation_summary"] = conv_summary

    # ── Run pipeline (with optional MLflow tracing) ───────────────
    result = None
    run_id = None
    latency = 0

    def _mlflow_reachable() -> bool:
        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("mlflow", 5000))
            s.close()
            return True
        except Exception:
            return False

    try:
        if not _mlflow_reachable():
            raise RuntimeError("MLflow not reachable")
        with mlflow.start_run() as run:
            run_id = run.info.run_id
            mlflow.set_tags(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "request_id": request_id,
                    "endpoint": "/chat",
                }
            )
            state["mlflow_run_id"] = run_id

            with mlflow.start_span(name="multi_agent_pipeline", span_type="CHAIN") as root_span:
                state["mlflow_trace_id"] = root_span.trace_id
                state["mlflow_span_id"] = root_span.span_id
                root_span.set_inputs({"message": body.message, "user_id": user_id})
                result = pipeline.invoke(state)
                root_span.set_outputs({"response": result.get("response", "")[:200]})
                root_span.set_attribute("intent", result.get("intent", ""))
                root_span.set_attribute("total_tokens", result["total_tokens"])
                root_span.set_attribute("total_cost_usd", result["total_cost_usd"])

            agent = result.get("intent", "unknown")
            mlflow.set_tag("agent_selected", agent)
            latency = (time.time() - start) * 1000
            mlflow.log_metrics(
                {
                    "total_tokens": result["total_tokens"],
                    "total_cost_usd": result["total_cost_usd"],
                    "latency_ms": latency,
                }
            )
            mlflow.log_table(
                data={
                    "role": ["user", "assistant"],
                    "content": [body.message, result.get("response", "")],
                    "agent": ["", result.get("intent", "")],
                    "tokens": [0, result["total_tokens"]],
                },
                artifact_file="chat_history.json",
            )

    except Exception as mlflow_err:
        log.warning(f"MLflow tracing unavailable: {mlflow_err}")
        if result is None:
            try:
                result = pipeline.invoke(state)
            except Exception as e:
                import traceback

                traceback.print_exc()
                log.error(f"Pipeline failed: {e}")
                ERROR_COUNT.labels(agent="unknown").inc()
                REQUEST_COUNT.labels(endpoint="/chat", agent="unknown", status="error").inc()
                raise HTTPException(status_code=500, detail=str(e))

    agent = result.get("intent", "unknown") if result else "unknown"
    if latency == 0:
        latency = (time.time() - start) * 1000

    # ── Prometheus metrics ────────────────────────────────────────
    REQUEST_COUNT.labels(endpoint="/chat", agent=agent, status="success").inc()
    REQUEST_LATENCY.labels(agent=agent).observe(time.time() - start)
    TOKEN_USAGE.labels(agent=agent).inc(result["total_tokens"])

    # ── Save assistant response ───────────────────────────────────
    save_message(
        session_id=session_id,
        role="assistant",
        content=result.get("response", ""),
        agent_name=result.get("intent"),
        token_usage={
            "total_tokens": result["total_tokens"],
            "total_cost_usd": result["total_cost_usd"],
        },
        mlflow_run_id=run_id,
    )

    # ── Update session ────────────────────────────────────────────
    update_session_agent(session_id, result.get("intent"))

    log.info(
        f"Response returned | intent={result.get('intent')} | "
        f"tokens={result['total_tokens']} | latency={latency:.0f}ms"
    )

    return ChatResponse(
        response=result.get("response", "I could not process your request."),
        session_id=session_id,
        intent=result.get("intent"),
        tokens_used=result["total_tokens"],
        cost_usd=result["total_cost_usd"],
    )
