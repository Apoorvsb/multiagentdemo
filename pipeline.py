
import mlflow
from typing import Literal
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
 # ← must be first

...
from state import AgentState, empty_state
from config import config
from logger import get_log
from mlflow_helpers import setup_mlflow
from agents.order_agent   import order_agent
from agents.product_agent import product_agent
from agents.support_agent import support_agent, _support_pending

setup_mlflow()

llm = ChatGroq(
    model=config.LLM_MODEL,
    temperature=0,
    api_key=config.GROQ_API_KEY
)


# ═══════════════════════════════════════════════════════
# INTENT ROUTER
# ═══════════════════════════════════════════════════════

class IntentOutput(BaseModel):
    intent: Literal["order_query", "product_query", "support_query"]


def intent_router(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "router", "intent_router")
    log.info("Node entered")

    # If this session is waiting for a support order selection, skip LLM routing
    if state["session_id"] in _support_pending:
        log.info("Session awaiting support order selection — routing to support_agent")
        return {**state, "intent": "support_query"}

    # Keyword shortcuts — catch common support/ticket queries before the LLM
    _msg = state["current_input"].lower()
    _SUPPORT_KEYWORDS = [
        # tickets
        "my tickets", "all tickets", "raised tickets", "show tickets",
        "list tickets", "ticket status", "my complaints",
        "tickets i have", "tickets i raised", "i have raised", "i raised a ticket",
        "show me the tickets", "show me tickets", "view tickets",
        "tickets raised", "have raised", "ticket i",
        # refund / payment
        "refund", "payment failed", "charged twice", "amount was deducted",
        "double charged", "wrong charge",
        # item issues
        "damaged", "cracked", "wrong item", "wrong product", "missing item",
        "item missing", "missing from my", "not as described", "not working as described",
        # warranty / technical
        "warranty claim", "warranty", "stopped working", "not working",
        "product stopped", "quality is poor", "poor quality",
        # account
        "cannot access my account", "can't access my account", "account access",
        "account blocked", "account locked", "login issue", "cant login",
        # cancellation / return
        "cancel my order", "cancel order", "want to cancel", "order cancellation",
        "return my order", "want to return", "return request", "send it back",
        "return the", "cancel the order", "i want to cancel", "i want to return",
        # general complaints / feedback
        "complaint", "not happy", "unhappy", "feedback", "packaging was bad",
        "bad packaging", "delivery experience", "is delayed", "order is delayed",
        "product quality", "poor service",
        "order is missing", "order missing", "package is missing", "package missing",
        "parcel missing", "shipment missing",
    ]
    if any(kw in _msg for kw in _SUPPORT_KEYWORDS):
        log.info("Keyword shortcut — routing to support_agent")
        return {**state, "intent": "support_query"}

    prompt = f"""Classify the user message into exactly one of these three intents:

- order_query: User is asking about THEIR OWN order, delivery, shipment, tracking, or purchase history.
  Examples: "where is my order", "when will it arrive", "track my package", "where is my RAM order",
  "where is my laptop", "my order is delayed", "show my orders", "did my phone arrive",
  "where is usb cable", "where is keyboard", "where is my headphones"
  KEY SIGNAL: words like "where is my", "where is", "my order", "my package", "my delivery"
  NOTE: "where is [product]" without buying context = order query (user asking about their purchase)

- product_query: User wants to FIND, BUY or get recommendations for a product.
  Examples: "find me a laptop", "best RAM under 2000", "recommend headphones", "show me keyboards",
  "suggest a good mouse", "what is the best cable"
  KEY SIGNAL: words like "find", "recommend", "best", "suggest", "show me", "buy"

- support_query: User has a complaint, issue, refund request, or needs help with a problem.
  Examples: "my item arrived damaged", "I want a refund", "wrong item delivered", "file a complaint"

User message: {state['current_input']}

IMPORTANT:
- "where is [product]" → order_query (asking about their order)
- "find me [product]" → product_query (shopping)
- "recommend [product]" → product_query (shopping)
- "eta of [product]" → order_query
- "arrival date of [product]" → order_query  
- "when does [product] arrive" → order_query
- "find me [product]" → product_query
- "recommend [product]" → product_query
-"show orders below 1000", "orders under 500", "orders above 5000",
    "orders costing more than 2000", "show orders below price"
KEY SIGNAL: 'orders above/below/under/over [number]' = order_query

Return only the intent label. Nothing else."""

    try:
        structured = llm.with_structured_output(IntentOutput)
        result     = structured.invoke(prompt)
        intent     = result.intent
    except Exception as e:
        log.error(f"Router failed: {e}")
        intent = "order_query"

    log.info(f"Intent classified: {intent}")
    return {**state, "intent": intent}


def route_to_agent(state: AgentState) -> str:
    return state.get("intent", "order_query")


# ═══════════════════════════════════════════════════════
# AGENT WRAPPERS
# ═══════════════════════════════════════════════════════

def run_order_agent(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "entry")
    log.info("Order agent started")
    result = order_agent.invoke(state)
    log.info("Order agent completed")
    return result


def run_product_agent(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "entry")
    log.info("Product agent started")
    result = product_agent.invoke(state)
    log.info("Product agent completed")
    return result


def run_support_agent(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "entry")
    log.info("Support agent started")
    result = support_agent.invoke(state)
    log.info("Support agent completed")
    return result


# ═══════════════════════════════════════════════════════
# BUILD PIPELINE GRAPH
# ═══════════════════════════════════════════════════════

def build_pipeline():
    graph = StateGraph(AgentState)

    graph.add_node("intent_router",  intent_router)
    graph.add_node("order_agent",    run_order_agent)
    graph.add_node("product_agent",  run_product_agent)
    graph.add_node("support_agent",  run_support_agent)

    graph.set_entry_point("intent_router")

    graph.add_conditional_edges("intent_router", route_to_agent, {
        "order_query":   "order_agent",
        "product_query": "product_agent",
        "support_query": "support_agent",
    })

    graph.add_edge("order_agent",   END)
    graph.add_edge("product_agent", END)
    graph.add_edge("support_agent", END)

    return graph.compile()


pipeline = build_pipeline()


# ═══════════════════════════════════════════════════════
# TEST BLOCK
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import uuid
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    test_messages = [
        "where is my order ORD0001",
        "find me a good cable under 500 rupees",
        "my laptop arrived with a cracked screen",
    ]

    for msg in test_messages:
        print(f"\n--- Testing: '{msg}' ---")
        state = empty_state(
            session_id    = session_id,
            user_id       = "test-user",
            request_id    = str(uuid.uuid4()),
            messages      = [],
            current_input = msg,
        )
        result = pipeline.invoke(state)
        print(f"Intent:   {result['intent']}")
        print(f"Response: {result.get('response', 'No response')[:150]}")