
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
from agents.support_agent import support_agent

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

    prompt = prompt = f"""Classify the user message into exactly one of these three intents:

- order_query: User is asking about THEIR OWN order, delivery, shipment, tracking, or purchase history. 
  Examples: "where is my order", "when will it arrive", "track my package", "where is my RAM order", 
  "where is my laptop", "my order is delayed", "show my orders", "did my phone arrive"
  KEY SIGNAL: words like "my order", "my package", "my delivery", "where is my [product]"

- product_query: User wants to FIND or BUY a product, get recommendations, or compare products.
  Examples: "find me a laptop", "best RAM under 2000", "recommend headphones", "show me keyboards"
  KEY SIGNAL: words like "find", "recommend", "best", "show me", "suggest", no ownership implied

- support_query: User has a complaint, issue, refund request, or needs help with a problem.
  Examples: "my item arrived damaged", "I want a refund", "wrong item delivered", "file a complaint"

User message: {state['current_input']}

IMPORTANT: If the user says "where is my [product]" or "my [product] order" — classify as order_query.
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