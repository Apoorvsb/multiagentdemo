import re
import mlflow
import psycopg2.extras
from database import get_conn
import json
from langchain_groq import ChatGroq
from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import log_llm_span, log_tool_span
from agents.shipment_subgraph import build_shipment_subgraph
from langgraph.graph import StateGraph, END
from database import save_message
from mlflow_helpers import calculate_cost, log_tool_span

llm = ChatGroq(
    model=config.LLM_MODEL,
    temperature=0,
    api_key=config.GROQ_API_KEY
)

print(" CONFIG MODEL =", config.LLM_MODEL)

# ─────────────────────────────────────────────
# NODE 1 — validate_input
# ─────────────────────────────────────────────

def validate_input(state: AgentState) -> AgentState:
    print("DEBUG current_input:", state["current_input"])  # add this
    msg = state["current_input"].upper()
    match = re.search(r'(ORD\d+)', msg)
    if not match:
        match = re.search(r'#?(\d{4,6})', msg)
    order_id = match.group(1) if match else None
    print("DEBUG order_id:", order_id)  # add this
    return {**state, "order_id": order_id}



def fetch_order_data(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "fetch_order_data")
    log.info("Tool called: fetch_order_data")
    order_id = state.get("order_id")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM orders WHERE order_id = %s",
                [order_id]
            )
            row = cur.fetchone()
            order = dict(row) if row else None

    log_tool_span(
        "fetch_order_data",
        "postgresql_orders_table",
        {"order_id": order_id},
        order,
    )
    log.info(f"Order found: {bool(order)}")
    return {**state, "order_data": order}

# ─────────────────────────────────────────────
# CONDITIONAL EDGE — order found or not
# ─────────────────────────────────────────────

def order_found_edge(state: AgentState) -> str:
    if state.get("order_data"):
        return "analyze_order_status"
    return "error_response"


# ─────────────────────────────────────────────
# NODE 3 — error_response
# ─────────────────────────────────────────────

def error_response(state: AgentState) -> AgentState:
    
    log = get_log(state["request_id"], "order_agent", "error_response")

    if state.get("response"):
        return state

    log.warning(f"Order not found: {state.get('order_id')}")

    log_tool_span(
        "error_response",
        "order_not_found",
        {"order_id": state.get("order_id")},
        {"message": "Order not found in database"},
    )

    return {
        **state,
        "response": f"Sorry, I could not find order #{state.get('order_id')}. Please check the order ID and try again.",
    }


# ─────────────────────────────────────────────
# NODE 4 — analyze_order_status
# ─────────────────────────────────────────────

def analyze_order_status(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "analyze_order_status")
    log.info("LLM called")

    prompt = f"""You are an order status assistant.
Order data: {state['order_data']}
Conversation history: {state['messages']}

Analyze the order status and explain:
1. Current status in plain English
2. Expected delivery date
3. Any delays or issues
4. What the customer should expect next"""

    with mlflow.start_span("analyze_order_status", span_type="LLM") as span:
        span.set_attribute("input",          state["current_input"])
        span.set_attribute("order_id",       state.get("order_id"))
        span.set_attribute("order_status",   state["order_data"].get("status"))
        span.set_attribute("prompt.name",    "order_analysis_prompt")
        span.set_attribute("prompt.version", config.ORDER_ANALYSIS_PROMPT_VERSION)

        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)

        span.set_attribute("llm.prompt",            prompt)
        span.set_attribute("llm.response",          response.content)
        span.set_attribute("llm.prompt_tokens",     input_tokens)
        span.set_attribute("llm.completion_tokens", output_tokens)
        span.set_attribute("llm.cost_usd",          cost)

    log.info("LLM completed")
    return {
        **state,
        "order_analysis": response.content,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


# ─────────────────────────────────────────────
# NODE 5 — generate_response
# ─────────────────────────────────────────────
def generate_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "generate_response")
    log.info("LLM called")

    prompt = f"""You are a helpful customer service assistant.
Order analysis: {state['order_analysis']}
Tracking info: {state['tracking_info']}
Customer asked: {state['current_input']}

Write a clear friendly response in 3-4 sentences.
Include current status, ETA, and tracking details."""

    with mlflow.start_span("generate_response", span_type="LLM") as span:
        span.set_attribute("input",          state["current_input"])
        span.set_attribute("prompt.name",    "response_generation_prompt")
        span.set_attribute("prompt.version", config.RESPONSE_GENERATION_PROMPT_VERSION)

        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)

        span.set_attribute("llm.prompt",            prompt)
        span.set_attribute("llm.response",          response.content)
        span.set_attribute("llm.prompt_tokens",     input_tokens)
        span.set_attribute("llm.completion_tokens", output_tokens)
        span.set_attribute("llm.cost_usd",          cost)

    log.info("Response generated")
    return {
        **state,
        "response":       response.content,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


# ─────────────────────────────────────────────
# NODE 6 — save_to_db
# ─────────────────────────────────────────────

def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "save_to_db")
    log.info("Saving response to DB")
    save_message(
        session_id    = state["session_id"],
        role          = "assistant",
        content       = state["response"],
        agent_name    = "order_agent",
        token_usage   = {
            "total_tokens":   state["total_tokens"],
            "total_cost_usd": state["total_cost_usd"],
        },
        mlflow_run_id = state.get("mlflow_run_id"),
    )
    log.info("Response saved")
    return state


# ─────────────────────────────────────────────
# BUILD ORDER AGENT GRAPH
# ─────────────────────────────────────────────
def build_order_agent():
    graph = StateGraph(AgentState)

    graph.add_node("validate_input",       validate_input)
    graph.add_node("fetch_order_data",     fetch_order_data)
    graph.add_node("analyze_order_status", analyze_order_status)
    graph.add_node("shipment_tracking",    build_shipment_subgraph())
    graph.add_node("generate_response",    generate_response)
    graph.add_node("save_to_db",           save_to_db)
    graph.add_node("error_response",       error_response)

    graph.set_entry_point("validate_input")

    graph.add_edge("validate_input", "fetch_order_data")

    graph.add_conditional_edges("fetch_order_data", order_found_edge, {
        "analyze_order_status": "analyze_order_status",
        "error_response":       "error_response",
    })

    graph.add_edge("analyze_order_status", "shipment_tracking")
    graph.add_edge("shipment_tracking",    "generate_response")
    graph.add_edge("generate_response",    "save_to_db")
    graph.add_edge("save_to_db",           END)
    graph.add_edge("error_response",       END)

    return graph.compile()


order_agent = build_order_agent()


# ─────────────────────────────────────────────
# TEST BLOCK
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    # Create user and session in DB first
    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    state = empty_state(
        session_id    = session_id,
        user_id       = "test-user",
        request_id    = "test-req-001",
        messages      = [],
        current_input = "where is my order #12345",
    )

    result = order_agent.invoke(state)
    print(f"\n=== RESULT ===")
    print(f"Order ID:  {result['order_id']}")
    print(f"Response:  {result['response']}")
    print(f"Tokens:    {result['total_tokens']}")
    print(f"Cost:      ${result['total_cost_usd']}")