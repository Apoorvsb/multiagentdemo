

import uuid
import time
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
# ── Prometheus metrics ─────────────────────────────────────
REQUEST_COUNT = Counter(
    "multiagent_requests_total",
    "Total requests",
    ["endpoint", "agent", "status"]
)
REQUEST_LATENCY = Histogram(
    "multiagent_request_latency_seconds",
    "Request latency in seconds",
    ["agent"]
)
TOKEN_USAGE = Counter(
    "multiagent_tokens_total",
    "Total tokens used",
    ["agent"]
)
ERROR_COUNT = Counter(
    "multiagent_errors_total",
    "Total errors",
    ["agent"]
)

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
            cur.execute(
                "SELECT * FROM sessions WHERE session_id = %s",
                [session_id]
            )
            row = cur.fetchone()
            return dict(row) if row else None


def update_user_metadata(user_id: str, metadata: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET metadata = %s WHERE user_id = %s",
                [psycopg2.extras.Json(metadata), user_id]
            )


def user_exists(user_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE user_id = %s",
                [user_id]
            )
            return cur.fetchone() is not None


# ═══════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    name:  str
    email: str


class LoginRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response:    str
    session_id:  str
    intent:      Optional[str]
    tokens_used: int
    cost_usd:    float


# ═══════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/register")
async def register(body: RegisterRequest):
    user_id = body.email

    if user_exists(user_id):
        session_id = get_or_create_session(None, user_id)
        return {
            "user_id":       user_id,
            "session_id":    session_id,
            "name":          body.name,
            "message":       "User already exists. Logged in successfully.",
            "existing_user": True
        }

    get_or_create_user(user_id)
    update_user_metadata(user_id, {"name": body.name, "email": body.email})
    session_id = get_or_create_session(None, user_id)

    return {
        "user_id":       user_id,
        "session_id":    session_id,
        "name":          body.name,
        "message":       "Registration successful.",
        "existing_user": False
    }


@app.post("/login")
async def login(body: LoginRequest):
    if not user_exists(body.user_id):
        raise HTTPException(
            status_code=404,
            detail={
                "error":      "User not found.",
                "action":     "Please sign up first.",
                "signup_url": "/register"
            }
        )

    session_id = get_or_create_session(None, body.user_id)
    return {
        "user_id":    body.user_id,
        "session_id": session_id,
        "message":    "Login successful.",
        "next_step":  "Use session_id in X-Session-ID header for /chat."
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body:         ChatRequest,
    x_session_id: Optional[str] = Header(None),
):
    if not x_session_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error":      "You are not logged in.",
                "message":    "Please sign up or log in to continue.",
                "signup_url": "/register",
                "login_url":  "/login",
            }
        )

    request_id = str(uuid.uuid4())
    log        = get_log(request_id)
    start      = time.time()

    # ── Load session ──────────────────────────────────────────────
    session_row = get_session_row(x_session_id)
    if not session_row:
        raise HTTPException(
            status_code=401,
            detail={
                "error":     "Session not found.",
                "message":   "Your session is invalid. Please log in again.",
                "login_url": "/login"
            }
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
                "error":     "Session expired.",
                "message":   "Your session has expired. Please log in again.",
                "login_url": "/login"
            }
        )

    # ── Load history ──────────────────────────────────────────────
    history = load_conversation_history(session_id)
    history = history[-10:]
    log.info(f"Session loaded | session_id={session_id} | history={len(history)} messages")

    # ── Save user message ─────────────────────────────────────────
    save_message(session_id=session_id, role="user", content=body.message)

    # ── Build state ───────────────────────────────────────────────
    state = empty_state(
        session_id    = session_id,
        user_id       = user_id,
        request_id    = request_id,
        messages      = history,
        current_input = body.message,
    )

    # ── Run pipeline under MLflow run ─────────────────────────────
    with mlflow.start_run() as run:
        run_id = run.info.run_id
        mlflow.set_tags({
            "session_id": session_id,
            "user_id":    user_id,
            "request_id": request_id,
            "endpoint":   "/chat",
        })

        state["mlflow_run_id"] = run_id

        try:
            # Capture trace context and propagate to LangGraph nodes
            from opentelemetry.propagate import inject, extract
            from opentelemetry import context as otel_context

            carrier = {}
            inject(carrier)

            with mlflow.start_span(name="multi_agent_pipeline", span_type="CHAIN") as root_span:
                state["mlflow_trace_id"] = root_span.trace_id
                state["mlflow_span_id"]  = root_span.span_id
                root_span.set_inputs({"message": body.message, "user_id": user_id})

                # Attach context so LangGraph nodes can find it
                ctx   = extract(carrier)
                token = otel_context.attach(ctx)
                try:
                    result = pipeline.invoke(state)
                finally:
                    otel_context.detach(token)
                root_span.set_outputs({"response": result.get("response", "")[:200]})
                root_span.set_attribute("intent",         result.get("intent", ""))
                root_span.set_attribute("total_tokens",   result["total_tokens"])
                root_span.set_attribute("total_cost_usd", result["total_cost_usd"])    

            mlflow.set_tag("agent_selected", result.get("intent", "unknown"))

        except Exception as e:
            import traceback
            traceback.print_exc()
            log.error(f"Pipeline failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        latency = (time.time() - start) * 1000
        mlflow.log_metrics({
            "total_tokens":   result["total_tokens"],
            "total_cost_usd": result["total_cost_usd"],
            "latency_ms":     latency,
        })
        mlflow.log_table(
        data={
            "role":    ["user",        "assistant"],
            "content": [body.message,  result.get("response", "")],
            "agent":   ["",            result.get("intent", "")],
            "tokens":  [0,             result["total_tokens"]],
        },
        artifact_file="chat_history.json"
    )

    # ── Save assistant response ───────────────────────────────────
    save_message(
        session_id    = session_id,
        role          = "assistant",
        content       = result.get("response", ""),
        agent_name    = result.get("intent"),
        token_usage   = {
            "total_tokens":   result["total_tokens"],
            "total_cost_usd": result["total_cost_usd"],
        },
        mlflow_run_id = run_id,
    )

    # ── Update session ────────────────────────────────────────────
    update_session_agent(session_id, result.get("intent"))

    log.info(
        f"Response returned | intent={result.get('intent')} | "
        f"tokens={result['total_tokens']} | latency={latency:.0f}ms"
    )

    return ChatResponse(
        response    = result.get("response", "I could not process your request."),
        session_id  = session_id,
        intent      = result.get("intent"),
        tokens_used = result["total_tokens"],
        cost_usd    = result["total_cost_usd"],
    )