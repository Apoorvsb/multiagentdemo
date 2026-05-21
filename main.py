import uuid
import time
import mlflow
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager

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


# ═══════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_mlflow()
    create_tables()
    yield


app = FastAPI(title="Multi-Agent App", version="1.0.0", lifespan=lifespan)


# ═══════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    user_id: str
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


# @app.post("/chat", response_model=ChatResponse)
# async def chat(
#     body: ChatRequest,
#     x_session_id: Optional[str] = Header(None),
# ):
#     request_id = str(uuid.uuid4())
#     log        = get_log(request_id)
#     start      = time.time()

#     log.info(f"Request received | user_id={body.user_id} | input='{body.message[:60]}'")

#     # Step 1 — ensure user exists
#     try:
#         get_or_create_user(body.user_id)
#     except Exception as e:
#         log.error(f"User DB error: {e}")
#         raise HTTPException(status_code=500, detail="Database error")

#     # Step 2 — load or create session
#     try:
#         session_id = get_or_create_session(x_session_id, body.user_id)
#     except ValueError as e:
#         log.warning(f"Session error: {e}")
#         raise HTTPException(status_code=400, detail=str(e))

#     # Step 3 — load conversation history
#     history = load_conversation_history(session_id)
#     log.info(f"Session loaded | session_id={session_id} | history={len(history)} messages")

#     # Step 4 — save user message
#     save_message(session_id=session_id, role="user", content=body.message)

   
#     # Step 5 — run pipeline under one MLflow run
#     with mlflow.start_run() as run:
#         mlflow.set_tags({
#             "session_id": session_id,
#             "user_id":    body.user_id,
#             "request_id": request_id,
#             "endpoint":   "/chat",
#         })

#     state = empty_state(
#         session_id    = session_id,
#         user_id       = body.user_id,
#         request_id    = request_id,
#         messages      = history,
#         current_input = body.message,
#         mlflow_run_id = run.info.run_id,
#     )

#     try:
#         with mlflow.start_run(name="full_request") as trace:
#             trace.set_attribute("user_message", body.message)
#             trace.set_attribute("user_id",      body.user_id)
#             trace.set_attribute("session_id",   session_id)

#             result = pipeline.invoke(state)

#             trace.set_attribute("intent",   result.get("intent", ""))
#             trace.set_attribute("response", result.get("response", ""))
#             trace.set_attribute("tokens",   result["total_tokens"])
#             trace.set_attribute("cost_usd", result["total_cost_usd"])

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         log.error(f"Pipeline failed: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

#     latency = (time.time() - start) * 1000
#     mlflow.log_metrics({
#         "total_tokens":   result["total_tokens"],
#         "total_cost_usd": result["total_cost_usd"],
#         "latency_ms":     latency,
#     })
#     # Step 6 — update session agent
#     update_session_agent(session_id, result.get("intent"))

#     log.info(
#         f"Response returned | intent={result.get('intent')} | "
#         f"tokens={result['total_tokens']} | latency={latency:.0f}ms"
#     )

#     # Step 7 — return response
#     return ChatResponse(
#         response    = result.get("response", "I could not process your request."),
#         session_id  = session_id,
#         intent      = result.get("intent"),
#         tokens_used = result["total_tokens"],
#         cost_usd    = result["total_cost_usd"],
#     )
@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    x_session_id: Optional[str] = Header(None),
):
    request_id = str(uuid.uuid4())
    log = get_log(request_id)
    start = time.time()

    log.info(
        f"Request received | user_id={body.user_id} | "
        f"input='{body.message[:60]}'"
    )

    # Step 1 — ensure user exists
    try:
        get_or_create_user(body.user_id)

    except Exception as e:
        log.error(f"User DB error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Database error"
        )

    # Step 2 — load or create session
    try:
        session_id = get_or_create_session(
            x_session_id,
            body.user_id
        )

    except ValueError as e:
        log.warning(f"Session error: {e}")

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # Step 3 — load conversation history
    history = load_conversation_history(session_id)

    log.info(
        f"Session loaded | "
        f"session_id={session_id} | "
        f"history={len(history)} messages"
    )

    # Step 4 — save user message
    save_message(
        session_id=session_id,
        role="user",
        content=body.message
    )

    try:

        # Step 5 — MLflow tracking
        with mlflow.start_run(run_name="full_request") as run:

            mlflow.set_tags({
                "session_id": session_id,
                "user_id": body.user_id,
                "request_id": request_id,
                "endpoint": "/chat",
            })

            mlflow.log_param(
                "user_message",
                body.message
            )

            # Build graph state
            state = empty_state(
                session_id=session_id,
                user_id=body.user_id,
                request_id=request_id,
                messages=history,
                current_input=body.message,
                mlflow_run_id=run.info.run_id,
            )

            # Execute pipeline
            result = pipeline.invoke(state)

            latency = (time.time() - start) * 1000

            # Log outputs
            mlflow.log_param(
                "intent",
                result.get("intent", "")
            )

            mlflow.log_param(
                "response",
                result.get("response", "")
            )

            # Metrics
            mlflow.log_metrics({
                "total_tokens": result.get("total_tokens", 0),
                "total_cost_usd": result.get("total_cost_usd", 0),
                "latency_ms": latency,
            })

    except Exception as e:
        import traceback

        traceback.print_exc()

        log.error(f"Pipeline failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    # Step 6 — save assistant response
    save_message(
        session_id=session_id,
        role="assistant",
        content=result.get("response", "")
    )

    # Step 7 — update session agent
    update_session_agent(
        session_id,
        result.get("intent")
    )

    log.info(
        f"Response returned | "
        f"intent={result.get('intent')} | "
        f"tokens={result.get('total_tokens', 0)} | "
        f"latency={latency:.0f}ms"
    )

    # Step 8 — return response
    return ChatResponse(
        response=result.get(
            "response",
            "I could not process your request."
        ),
        session_id=session_id,
        intent=result.get("intent"),
        tokens_used=result.get("total_tokens", 0),
        cost_usd=result.get("total_cost_usd", 0),
    )