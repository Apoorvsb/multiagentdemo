import mlflow
from typing import Literal
from pydantic import BaseModel
from langgraph.graph import StateGraph, END

from langchain_groq import ChatGroq
from state import AgentState, empty_state
from config import config
from logger import get_log
from mlflow_helpers import log_llm_span, setup_mlflow
from agents.order_agent import order_agent

setup_mlflow()
llm=ChatGroq(
    model=config.LLM_MODEL,
    temperature=0,
    api_key=config.GROQ_API_KEY
)


class IntentOutput(BaseModel):
    intent: Literal["order_query", "product_query", "support_query"]

# ═══════════════════════════════════════════════════════
# INTENT ROUTER
# ═══════════════════════════════════════════════════════

def intent_router(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "router", "intent_router")
    log.info("Node entered")

    prompt = f"""Classify the user message into exactly one of these three intents:
- order_query   (tracking, delivery, shipment, order status)
- product_query (find products, recommendations, specs, price)
- support_query (complaints, refunds, damaged items, policy)

User message: {state['current_input']}

Return only the intent label. Nothing else."""

    structured = llm.with_structured_output(IntentOutput)
    result     = structured.invoke(prompt)

    log.info(f"Intent classified: {result.intent}")
   
    
    
    log_llm_span(
        "intent_router",
        prompt,
        result.intent,
        0, 0,
        config.LLM_MODEL,
        "intent_router_prompt",
        1,
    )

    log.info(f"Intent classified: {result.intent}")
    return {**state, "intent": result.intent}


def route_to_agent(state: AgentState) -> str:
    return state.get("intent", "order_query")








# ═══════════════════════════════════════════════════════
# PLACEHOLDERS — agents not built yet
# ═══════════════════════════════════════════════════════

def product_agent_placeholder(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "placeholder")
    log.info("Product agent not built yet")
    return {**state, "response": "This agent is not yet available. We are working on it."}


def support_agent_placeholder(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "placeholder")
    log.info("Support agent not built yet")
    return {**state, "response": "This agent is not yet available. We are working on it."}


# ═══════════════════════════════════════════════════════
# ORDER AGENT WRAPPER
# Calls the full order_agent graph as a single node
# ═══════════════════════════════════════════════════════

def run_order_agent(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "entry")
    log.info("Order agent started")
    result = order_agent.invoke(state)
    log.info("Order agent completed")
    return result


# ═══════════════════════════════════════════════════════
# BUILD PIPELINE GRAPH
# ═══════════════════════════════════════════════════════

def build_pipeline():
    graph = StateGraph(AgentState)

    graph.add_node("intent_router",  intent_router)
    graph.add_node("order_agent",    run_order_agent)
    graph.add_node("product_agent",  product_agent_placeholder)
    graph.add_node("support_agent",  support_agent_placeholder)

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
        "where is my order #12345",
        "find me a laptop under 50000",
        "my item arrived damaged",
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
        print(f"Response: {result['response']}")