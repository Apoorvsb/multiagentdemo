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

from mlflow_helpers import calculate_cost, log_tool_span, log_llm_span

import state

llm = ChatGroq(
    model=config.LLM_MODEL,
    temperature=0,
    api_key=config.GROQ_API_KEY
)

print(" CONFIG MODEL =", config.LLM_MODEL)

# ─────────────────────────────────────────────
# NODE 1 — validate_input
# ─────────────────────────────────────────────

# def validate_input(state: AgentState) -> AgentState:
#     print("DEBUG current_input:", state["current_input"])  # add this
#     msg = state["current_input"].upper()
#     match = re.search(r'(ORD\d+)', msg)
#     if not match:
#        match = re.search(r'#?(\d{3,6})', msg)
#     order_id = match.group(1) if match else None
#     print("DEBUG order_id:", order_id)  # add this
#     return {**state, "order_id": order_id}
def validate_input(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "validate_input")
    log.info("Node entered")

    msg   = state["current_input"].upper()
    match = re.search(r'(ORD\d+)', msg)
    if not match:
        match = re.search(r'#?(\d{3,6})', msg)

    order_id = match.group(1) if match else None
    log.info(f"Extracted order_id={order_id}")

    # Has order ID — proceed normally
    if order_id:
        return {**state, "order_id": order_id}

    # ── No order ID — check if follow-up about previous order ──
    user_id   = state.get("user_id")
    msg_lower = state["current_input"].lower()

    followup_keywords = ["when will", "when does", "where is it", "will it arrive",
                         "eta", "status", "how long", "update", "track it"]
    is_followup = any(kw in msg_lower for kw in followup_keywords)
    if is_followup and state.get("messages"):
        for msg_item in reversed(state["messages"][-6:]):
            content = msg_item.get("content", "").upper()
            prev_match = re.search(r'(ORD\d+)', content)
            if prev_match:
                order_id = prev_match.group(1)
                log.info(f"Follow-up detected — reusing order_id={order_id}")
                return {**state, "order_id": order_id}

    # ── Detect special queries ────────────────────────────
    special_response = None

    if any(w in msg_lower for w in ["how many", "count", "total orders", "number of orders"]):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", [user_id])
                total = cur.fetchone()[0]
                cur.execute(
                    "SELECT status, COUNT(*) FROM orders WHERE user_id = %s GROUP BY status ORDER BY COUNT(*) DESC",
                    [user_id]
                )
                breakdown = cur.fetchall()
        breakdown_lines = "\n".join([f"  • {s}: {c}" for s, c in breakdown])
        special_response = f"You have {total} orders in total.\n\nBreakdown:\n{breakdown_lines}"

    elif any(w in msg_lower for w in ["cheapest", "lowest price", "least expensive"]):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer ASC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
        special_response = f"Here are your cheapest orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."

    elif any(w in msg_lower for w in ["expensive", "highest price", "most expensive", "costliest"]):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer DESC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
        special_response = f"Here are your most expensive orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."

    elif any(w in msg_lower for w in ["last week", "this week", "past week"]):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY order_date DESC LIMIT 10",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            special_response = "You have no orders from the last week."
        else:
            lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
            special_response = f"Here are your orders from the last week:\n\n{lines}\n\nReply with an Order ID to get full tracking details."

    elif any(w in msg_lower for w in ["last month", "this month", "past month"]):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '30 days' ORDER BY order_date DESC LIMIT 10",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            special_response = "You have no orders from the last month."
        else:
            lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
            special_response = f"Here are your orders from the last month:\n\n{lines}\n\nReply with an Order ID to get full tracking details."

    elif any(w in msg_lower for w in ["late risk", "delayed risk", "at risk", "risky", "might be late"]):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items FROM orders WHERE user_id = %s AND late_delivery_risk = 1 ORDER BY order_date DESC LIMIT 10",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            special_response = "None of your orders have a late delivery risk."
        else:
            lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Delivery: {o['estimated_delivery']}) — Items: {o['items']}" for o in orders])
            special_response = f"These orders have a late delivery risk:\n\n{lines}\n\nReply with an Order ID for full details."

    if special_response:
        return {**state, "order_id": None, "response": special_response}

    # ── Semantic status detection ─────────────────────────
    status_map = {
        "in transit":       "IN_TRANSIT",
        "transit":          "IN_TRANSIT",
        "on the way":       "IN_TRANSIT",
        "shipped":          "IN_TRANSIT",
        "on its way":       "IN_TRANSIT",
        "out for delivery": "OUT_FOR_DELIVERY",
        "out":              "OUT_FOR_DELIVERY",
        "delivering":       "OUT_FOR_DELIVERY",
        "with delivery":    "OUT_FOR_DELIVERY",
        "delivered":        "DELIVERED",
        "received":         "DELIVERED",
        "arrived":          "DELIVERED",
        "completed":        "DELIVERED",
        "got it":           "DELIVERED",
        "pending":          "PENDING",
        "not shipped":      "PENDING",
        "processing":       "PENDING",
        "waiting":          "PENDING",
        "delayed":          "DELAYED",
        "late":             "DELAYED",
        "stuck":            "DELAYED",
        "slow":             "DELAYED",
        "not moving":       "DELAYED",
        "returned":         "RETURNED",
        "sent back":        "RETURNED",
        "refunded":         "RETURNED",
        "rejected":         "RETURNED",
    }

    status_filter = None
    for phrase, status in status_map.items():
        if phrase in msg_lower:
            status_filter = status
            break

    # ── Semantic product detection from DB ────────────────
    from difflib import get_close_matches
    import json as _json

    product_keyword = None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT items::text FROM orders WHERE user_id = %s",
                    [user_id]
                )
                all_items = [row[0] for row in cur.fetchall()]

        product_names = set()
        for item_str in all_items:
            try:
                items = _json.loads(item_str)
                if isinstance(items, list):
                    for item in items:
                        for word in item.lower().split():
                            if len(word) > 2:
                                product_names.add(word)
                        product_names.add(item.lower())
            except:
                pass

        msg_words = [w.strip("?.,!") for w in msg_lower.split() if len(w.strip("?.,!")) > 2]
        for word in msg_words:
            for product in product_names:
                if word in product or product in word:
                    product_keyword = product
                    break
            if product_keyword:
                break
            matches = get_close_matches(word, product_names, n=1, cutoff=0.75)
            if matches:
                product_keyword = matches[0]
                break

    except Exception as e:
        log.error(f"Semantic product detection error: {e}")

    # ── Query DB ──────────────────────────────────────────
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if status_filter and product_keyword:
                cur.execute(
                    """SELECT order_id, status, carrier, estimated_delivery, items
                       FROM orders WHERE user_id = %s AND status = %s
                       AND items::text ILIKE %s
                       ORDER BY order_date DESC LIMIT 10""",
                    [user_id, status_filter, f"%{product_keyword}%"]
                )
                orders = [dict(r) for r in cur.fetchall()]
                if not orders:
                    cur.execute(
                        """SELECT order_id, status, carrier, estimated_delivery, items
                           FROM orders WHERE user_id = %s AND status = %s
                           ORDER BY order_date DESC LIMIT 10""",
                        [user_id, status_filter]
                    )
                    orders = [dict(r) for r in cur.fetchall()]

            elif status_filter:
                cur.execute(
                    """SELECT order_id, status, carrier, estimated_delivery, items
                       FROM orders WHERE user_id = %s AND status = %s
                       ORDER BY order_date DESC LIMIT 10""",
                    [user_id, status_filter]
                )
                orders = [dict(r) for r in cur.fetchall()]

            elif product_keyword:
                cur.execute(
                    """SELECT order_id, status, carrier, estimated_delivery, items
                       FROM orders WHERE user_id = %s
                       AND items::text ILIKE %s
                       ORDER BY order_date DESC LIMIT 10""",
                    [user_id, f"%{product_keyword}%"]
                )
                orders = [dict(r) for r in cur.fetchall()]
                if not orders:
                    return {
                        **state,
                        "order_id": None,
                        "response": f"I could not find any orders containing '{product_keyword}' in your account. Would you like to see all your recent orders instead?"
                    }

            else:
                cur.execute(
                    """SELECT order_id, status, carrier, estimated_delivery, items
                       FROM orders WHERE user_id = %s
                       ORDER BY order_date DESC LIMIT 10""",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]

    if not orders:
        return {
            **state,
            "order_id": None,
            "response": "You have no orders in our system yet."
        }

    lines = "\n".join([
        f"• {o['order_id']} — {o['status']} via {o['carrier']} "
        f"(Delivery: {o['estimated_delivery']}) — Items: {o['items']}"
        for o in orders
    ])

    return {
        **state,
        "order_id": None,
        "response": (
            f"Here are your matching orders:\n\n{lines}\n\n"
            f"Which order would you like to track? Reply with the Order ID (e.g. ORD2001)."
        )
    }
def fetch_order_data(state: AgentState) -> AgentState:
    print(f"DEBUG trace_id: {state.get('mlflow_trace_id')}")
    print(f"DEBUG span_id:  {state.get('mlflow_span_id')}")
    log = get_log(state["request_id"], "order_agent", "fetch_order_data")
    log.info("Tool called: fetch_order_data")
    order_id = state.get("order_id")
    user_id  = state.get("user_id")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM orders WHERE order_id = %s",
                [order_id]
            )
            row   = cur.fetchone()
            order = dict(row) if row else None

    # Order does not exist
    if not order:
        log.warning(f"Order not found: {order_id}")
        log_tool_span(
            "fetch_order_data",
            "postgresql_orders_table",
            {"order_id": order_id},
            {"found": False, "reason": "not_found"},
        )
        return {**state, "order_data": None}

    # Order belongs to a different user
    if order.get("user_id") and order.get("user_id") != user_id:
        log.warning(f"Order {order_id} does not belong to user {user_id}")
        log_tool_span(
            "fetch_order_data",
            "postgresql_orders_table",
            {"order_id": order_id},
            {"found": False, "reason": "unauthorized"},
        )
        return {**state, "order_data": None}

    # Order found and authorized
    log.info(f"Order found and authorized: {order_id}")
    log_tool_span(
    "fetch_order_data",
    "postgresql_orders_table",
    {"order_id": order_id},
    {"found": True, "order": str(order)},
    trace_id  = state.get("mlflow_trace_id"),
    parent_id = state.get("mlflow_span_id"),
)
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

    prompt_template = mlflow.genai.load_prompt(f"prompts:/order_analysis_prompt/{config.ORDER_ANALYSIS_PROMPT_VERSION}")
    prompt = prompt_template.format(
        order_data = str(state['order_data']),
        history    = str(state['messages']),
    )

    response      = llm.invoke(prompt)
    usage         = response.usage_metadata
    input_tokens  = usage.get("input_tokens",  0)
    output_tokens = usage.get("output_tokens", 0)
    cost          = log_llm_span(
        span_name      = "analyze_order_status",
        prompt_text    = prompt,
        response_text  = response.content,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "order_analysis_prompt",
        prompt_version = config.ORDER_ANALYSIS_PROMPT_VERSION,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

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

    prompt_template = mlflow.genai.load_prompt(f"prompts:/response_generation_prompt/{config.RESPONSE_GENERATION_PROMPT_VERSION}")
    prompt = prompt_template.format(
        order_analysis = str(state['order_analysis']),
        tracking_info  = str(state['tracking_info']),
        question       = state['current_input'],
    )

    response      = llm.invoke(prompt)
    usage         = response.usage_metadata
    input_tokens  = usage.get("input_tokens",  0)
    output_tokens = usage.get("output_tokens", 0)
    cost          = log_llm_span(
        span_name      = "generate_response",
        prompt_text    = prompt,
        response_text  = response.content,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "response_generation_prompt",
        prompt_version = config.RESPONSE_GENERATION_PROMPT_VERSION,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

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