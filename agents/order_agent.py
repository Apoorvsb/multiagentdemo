import re
import json as _json
import uuid
import calendar
import mlflow
import psycopg2.extras
from datetime import date as _date, timedelta as _td
from typing import Optional
from database import get_conn, save_message
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import log_llm_span, log_tool_span
from agents.shipment_subgraph import build_shipment_subgraph
from langgraph.graph import StateGraph, END

llm = ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────


def group_orders_by_status(orders: list) -> str:
    status_order = ["DELAYED", "PENDING", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"]
    emoji_map = {
        "DELAYED": "🔴",
        "PENDING": "🟡",
        "IN_TRANSIT": "🚚",
        "OUT_FOR_DELIVERY": "📦",
        "DELIVERED": "✅",
        "RETURNED": "↩️",
    }
    grouped = {}
    for o in orders:
        s = o["status"]
        if s not in grouped:
            grouped[s] = []
        grouped[s].append(o)

    def _fmt_order(o):
        placed = f" | Placed: {o['order_date']}" if o.get("order_date") else ""
        return (
            f"  • {o['order_id']} — via {o['carrier']}"
            f"{placed} (Delivery: {o['estimated_delivery']})"
            f" — ₹{o.get('sales_per_customer', 'N/A')} — Items: {o['items']}"
        )

    sections = []
    for status in status_order:
        if status in grouped:
            lines = "\n".join([_fmt_order(o) for o in grouped[status]])
            sections.append(f"{emoji_map.get(status, '•')} **{status.replace('_', ' ')}**\n{lines}")

    for status, grp_items in grouped.items():
        if status not in status_order:
            lines = "\n".join([_fmt_order(o) for o in grp_items])
            sections.append(f"• **{status}**\n{lines}")

    return "\n\n".join(sections)


# ─────────────────────────────────────────────
# TOOL — fetch_orders (@tool + ToolNode)
# ─────────────────────────────────────────────


@tool
def fetch_orders(
    user_id: str,
    order_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    product_keyword: Optional[str] = None,
    carrier_filter: Optional[str] = None,
    shipping_mode: Optional[str] = None,
    city_filter: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 10,
    date_filter: Optional[str] = None,
    month_filter: Optional[int] = None,
    year_filter: Optional[int] = None,
    special_query: Optional[str] = None,
) -> str:
    """Query the PostgreSQL orders table and return matching orders as JSON.

    Use special_query for preset queries: 'count', 'cheapest', 'most_expensive',
    'last_week', 'last_month', 'late_risk', 'upcoming', 'recent', 'oldest'.
    All other params act as AND filters on the orders table.
    Returns a JSON string with keys: type, orders, count, single_order, error.
    """
    try:
        result = _execute_order_query(
            user_id=user_id,
            order_id=order_id,
            status_filter=status_filter,
            product_keyword=product_keyword,
            carrier_filter=carrier_filter,
            shipping_mode=shipping_mode,
            city_filter=city_filter,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            date_filter=date_filter,
            month_filter=month_filter,
            year_filter=year_filter,
            special_query=special_query,
        )
        return _json.dumps(result, default=str)
    except Exception as e:
        return _json.dumps({"type": "error", "error": str(e), "orders": []})


_ITEMS_VARIANTS: dict[str, str] = {
    "smartwatch": "smart watch",
    "smart watch": "smartwatch",
    "smartphone": "smart phone",
    "smart phone": "smartphone",
    "powerbank": "power bank",
    "power bank": "powerbank",
    "smarttv": "smart tv",
    "smart tv": "smarttv",
}


def _items_cond(pk: str) -> tuple[str, list]:
    """Return (condition_sql, params) for items ILIKE, covering compound-word variants."""
    alt = _ITEMS_VARIANTS.get(pk.lower())
    if alt:
        return "(items::text ILIKE %s OR items::text ILIKE %s)", [f"%{pk}%", f"%{alt}%"]
    return "items::text ILIKE %s", [f"%{pk}%"]


def _execute_order_query(
    user_id: str,
    order_id=None,
    status_filter=None,
    product_keyword=None,
    carrier_filter=None,
    shipping_mode=None,
    city_filter=None,
    min_price=None,
    max_price=None,
    limit=10,
    date_filter=None,
    month_filter=None,
    year_filter=None,
    special_query=None,
) -> dict:
    """Pure DB query — returns a dict, no state/response logic."""

    # ── Single order by ID ───────────────────────────────────
    if order_id:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM orders WHERE order_id = %s", [order_id])
                row = cur.fetchone()
        if not row:
            return {"type": "not_found", "order_id": order_id, "orders": []}
        order = dict(row)
        if order.get("user_id") and order.get("user_id") != user_id:
            return {"type": "unauthorized", "order_id": order_id, "orders": []}
        return {"type": "single_order", "single_order": order, "orders": [order]}

    # ── Shared date condition builder ────────────────────────
    import re as _re

    def _date_conds(conds, params):
        nonlocal month_filter, year_filter
        # Detect partial date like "2026-06" (YYYY-MM) — treat as month+year filter
        if date_filter and _re.match(r"^\d{4}-\d{2}$", str(date_filter)):
            _y, _m = str(date_filter).split("-")
            month_filter = int(_m)
            year_filter = int(_y)
        # If month_filter is set, use it (even if date_filter also set — LLM sometimes sets both).
        if month_filter and year_filter:
            conds.append("EXTRACT(MONTH FROM order_date::date) = %s AND EXTRACT(YEAR FROM order_date::date) = %s")
            params.extend([month_filter, year_filter])
        elif month_filter and not date_filter:
            conds.append("EXTRACT(MONTH FROM order_date::date) = %s")
            params.append(month_filter)
        elif year_filter and not date_filter:
            conds.append("EXTRACT(YEAR FROM order_date::date) = %s")
            params.append(year_filter)
        elif date_filter and not month_filter:
            conds.append("order_date::date = %s")
            params.append(date_filter)

    # ── Count ────────────────────────────────────────────────
    if special_query == "count":
        conds, params = ["user_id = %s"], [user_id]
        if product_keyword:
            _cond, _p = _items_cond(product_keyword)
            conds.append(_cond)
            params.extend(_p)
        if carrier_filter:
            conds.append("carrier ILIKE %s")
            params.append(f"%{carrier_filter}%")
        if status_filter:
            conds.append("status = %s")
            params.append(status_filter)
        if shipping_mode:
            conds.append("shipping_mode ILIKE %s")
            params.append(f"%{shipping_mode}%")
        if city_filter:
            conds.append("order_city ILIKE %s")
            params.append(f"%{city_filter}%")
        if min_price:
            conds.append("sales_per_customer >= %s")
            params.append(float(min_price))
        if max_price:
            conds.append("sales_per_customer <= %s")
            params.append(float(max_price))
        _date_conds(conds, params)
        where = " AND ".join(conds)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM orders WHERE {where}", params)
                total = cur.fetchone()[0]
                cur.execute(
                    f"SELECT status, COUNT(*) FROM orders WHERE {where} GROUP BY status ORDER BY COUNT(*) DESC",
                    params,
                )
                breakdown = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]
        return {
            "type": "count",
            "total": total,
            "breakdown": breakdown,
            "filters": {
                "product_keyword": product_keyword,
                "carrier_filter": carrier_filter,
                "status_filter": status_filter,
                "shipping_mode": shipping_mode,
            },
            "orders": [],
        }

    # ── Price extremes ────────────────────────────────────────
    if special_query in ("cheapest", "most_expensive"):
        conds, params = ["user_id = %s"], [user_id]
        _date_conds(conds, params)
        order_dir = "ASC" if special_query == "cheapest" else "DESC"
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT order_id, status, carrier, items, sales_per_customer, order_date "
                    f"FROM orders WHERE {' AND '.join(conds)} "
                    f"ORDER BY sales_per_customer {order_dir} NULLS LAST LIMIT 5",
                    params,
                )
                orders = [dict(r) for r in cur.fetchall()]
        return {"type": special_query, "orders": orders}

    # ── Time-based presets ────────────────────────────────────
    preset_sql = {
        "last_week": (
            "SELECT order_id, status, carrier, estimated_delivery, items, order_date "
            "FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '7 days' "
            "ORDER BY order_date DESC LIMIT 10"
        ),
        "last_month": (
            "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders "
            "WHERE user_id = %s "
            "AND EXTRACT(YEAR FROM order_date::date) = EXTRACT(YEAR FROM CURRENT_DATE - INTERVAL '1 month') "
            "AND EXTRACT(MONTH FROM order_date::date) = EXTRACT(MONTH FROM CURRENT_DATE - INTERVAL '1 month') "
            "ORDER BY order_date DESC LIMIT 50"
        ),
        "late_risk": (
            "SELECT order_id, status, carrier, estimated_delivery, items, sales_per_customer "
            "FROM orders WHERE user_id = %s AND status NOT IN ('DELIVERED','RETURNED') "
            "ORDER BY order_date DESC LIMIT 10"
        ),
        "upcoming": (
            "SELECT order_id, status, carrier, estimated_delivery, items, sales_per_customer "
            "FROM orders WHERE user_id = %s AND status NOT IN ('DELIVERED','RETURNED') "
            "ORDER BY order_date DESC LIMIT 10"
        ),
        "recent": (
            "SELECT order_id, status, carrier, estimated_delivery, items, order_date "
            "FROM orders WHERE user_id = %s ORDER BY order_date DESC LIMIT 5"
        ),
        "oldest": (
            "SELECT order_id, status, carrier, estimated_delivery, items, order_date "
            "FROM orders WHERE user_id = %s ORDER BY order_date ASC LIMIT 5"
        ),
    }
    if special_query in preset_sql:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(preset_sql[special_query], [user_id])
                orders = [dict(r) for r in cur.fetchall()]
        return {"type": special_query, "orders": orders}

    # ── General filter query ──────────────────────────────────
    conds, params = ["user_id = %s"], [user_id]
    if status_filter:
        conds.append("status = %s")
        params.append(status_filter)
    if product_keyword:
        _cond, _p = _items_cond(product_keyword)
        conds.append(_cond)
        params.extend(_p)
    if carrier_filter:
        conds.append("carrier ILIKE %s")
        params.append(f"%{carrier_filter}%")
    if shipping_mode:
        conds.append("shipping_mode ILIKE %s")
        params.append(f"%{shipping_mode}%")
    if city_filter:
        conds.append("order_city ILIKE %s")
        params.append(f"%{city_filter}%")
    if min_price:
        conds.append("sales_per_customer >= %s")
        params.append(float(min_price))
    if max_price:
        conds.append("sales_per_customer <= %s")
        params.append(float(max_price))
    _date_conds(conds, params)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT order_id, status, carrier, estimated_delivery, items, "
                f"sales_per_customer, order_date FROM orders WHERE {' AND '.join(conds)} "
                f"ORDER BY order_date DESC LIMIT {limit}",
                params,
            )
            orders = [dict(r) for r in cur.fetchall()]
    return {
        "type": "filter",
        "orders": orders,
        "filters": {
            "status_filter": status_filter,
            "product_keyword": product_keyword,
            "carrier_filter": carrier_filter,
            "shipping_mode": shipping_mode,
            "city_filter": city_filter,
            "min_price": min_price,
            "max_price": max_price,
            "date_filter": date_filter,
            "month_filter": month_filter,
            "year_filter": year_filter,
        },
    }


# ToolNode wrapping the fetch_orders tool
order_tool_node = ToolNode([fetch_orders])


# ─────────────────────────────────────────────
# NODE 1 — validate_input (LLM ONLY)
# ─────────────────────────────────────────────


def validate_input(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "validate_input")
    log.info("Node entered")

    msg_lower = state["current_input"].lower()
    msg_upper = state["current_input"].upper()

    # ── Greetings / conversational messages (no DB needed) ────
    _GOODBYE_PATTERNS = [
        r"\bbye\b",
        r"\bgoodbye\b",
        r"\bsee you\b",
        r"\bsee ya\b",
        r"\bcya\b",
        r"\bttyl\b",
        r"\btake care\b",
        r"\bgood night\b",
    ]
    if any(re.search(p, msg_lower) for p in _GOODBYE_PATTERNS):
        log.info("Goodbye detected")
        return {
            **state,
            "order_id": None,
            "response": "Goodbye! Feel free to come back anytime if you need help with your orders. Have a great day!",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _THANKS_PATTERNS = [
        r"\bthank(?:s| you| u)\b",
        r"\bthx\b",
        r"\bty\b",
        r"\bcheers\b",
        r"\bappreciate\b",
    ]
    if any(re.search(p, msg_lower) for p in _THANKS_PATTERNS):
        log.info("Thanks detected")
        return {
            **state,
            "order_id": None,
            "response": "You're welcome! Is there anything else you'd like to know about your orders?",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _HOW_ARE_YOU_PATTERNS = [
        r"\bhow are you\b",
        r"\bhow r u\b",
        r"\bhow(?:'s| is) it going\b",
        r"\bhow(?:'re| are) you doing\b",
        r"\bhow have you been\b",
        r"\bhow do you do\b",
        r"\bwhat'?s up\b",
        r"\bwassup\b",
    ]
    if any(re.search(p, msg_lower) for p in _HOW_ARE_YOU_PATTERNS):
        log.info("How-are-you detected")
        return {
            **state,
            "order_id": None,
            "response": (
                "I'm doing great, thanks for asking! I'm here to help with your orders.\n\n"
                "- **Track an order** — share your Order ID (e.g. ORD12345)\n"
                "- **Check delivery status** — pending, in-transit, delivered, delayed\n"
                "- **Browse order history** — filter by carrier, product, price, or date"
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _GREETING_PATTERNS = [
        r"\bhi\b",
        r"\bhello\b",
        r"\bhey\b",
        r"\bhiya\b",
        r"\bhowdy\b",
        r"\bgreetings\b",
        r"\bgood\s+(?:morning|afternoon|evening)\b",
        r"\bwho are you\b",
        r"\bwhat are you\b",
        r"\bwhat can you do\b",
        r"\bwhat do you do\b",
        r"\bintroduce yourself\b",
    ]
    if any(re.search(p, msg_lower) for p in _GREETING_PATTERNS):
        log.info("Greeting detected — returning order assistant intro")
        return {
            **state,
            "order_id": None,
            "response": (
                "Hi! I'm your order assistant. I can help you:\n\n"
                "- **Track an order** — share your Order ID (e.g. ORD12345)\n"
                "- **View order status** — pending, in-transit, delivered, delayed\n"
                "- **Browse all your orders** — filter by carrier, product, price, or date\n\n"
                "What would you like to know about your orders?"
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # ── Block guest users ─────────────────────────────────
    user_id = state.get("user_id", "")
    if user_id.endswith("@guest.com"):
        return {
            **state,
            "order_id": None,
            "response": (
                "🚫 You don't have access to order information.\n\n"
                "Please **sign up** at /register with your email to track orders, "
                "view delivery status, and manage your purchases."
            ),
        }

    # ── Check explicit order ID first (no LLM needed) ────
    match = re.search(r"(ORD\d+)", msg_upper)
    if match:
        log.info(f"Explicit order ID found: {match.group(1)}")
        return {
            **state,
            "order_id": match.group(1),
            "status_filter": None,
            "product_keyword": None,
            "special_query": None,
            "carrier_filter": None,
            "shipping_mode": None,
            "city_filter": None,
            "min_price": None,
            "max_price": None,
            "query_limit": 10,
            "date_filter": None,
            "month_filter": None,
            "year_filter": None,
        }

    # ── Check follow-up from history (no LLM needed) ─────
    followup_keywords = [
        "when will",
        "when does",
        "when it",
        "when was",
        "when did",
        "where is it",
        "will it arrive",
        "eta",
        "how long",
        "update",
        "delivery date",
        "tracking number",
        "current status",
        "what happened",
        "latest update",
        "track it",
        "has it",
        "did it",
        "what is the status",
        "what's the status",
        "status of",
        "tell me the status",
        "give me the status",
        "any update",
        "where is it now",
        "tell me more",
        "more details",
        "more info",
        "show details",
        "give me details",
        "is it delivered",
        "has it arrived",
        "what is the order",
        "order id",
        "order number",
        "give me the order",
        "what is the id",
        "tell me the order",
    ]
    is_followup = any(kw in msg_lower for kw in followup_keywords)

    msg_words = [w for w in msg_lower.split() if len(w) > 3]
    stop_words = {
        "what",
        "when",
        "where",
        "show",
        "list",
        "give",
        "tell",
        "find",
        "order",
        "orders",
        "will",
        "does",
        "have",
        "that",
        "this",
        "your",
        "mine",
    }
    content_words = [w for w in msg_words if w not in stop_words]
    has_product_mention = len(content_words) > 1 or (
        len(content_words) > 0 and not any(kw in msg_lower for kw in followup_keywords)
    )

    if is_followup and not has_product_mention and state.get("messages"):
        for msg_item in reversed(state["messages"]):
            content = msg_item.get("content", "").upper()
            prev_match = re.search(r"(ORD\d+)", content)
            if prev_match:
                order_id = prev_match.group(1)
                log.info(f"Follow-up detected — reusing order_id={order_id}")
                return {
                    **state,
                    "order_id": order_id,
                    "status_filter": None,
                    "product_keyword": None,
                    "special_query": None,
                    "carrier_filter": None,
                    "shipping_mode": None,
                    "city_filter": None,
                    "min_price": None,
                    "max_price": None,
                    "query_limit": 10,
                    "date_filter": None,
                    "month_filter": None,
                    "year_filter": None,
                }

    # ── Fetch product names for LLM context only ─────────
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT items::text FROM orders WHERE user_id = %s", [user_id])
                all_items = [row[0] for row in cur.fetchall()]
        product_names = set()
        for item_str in all_items:
            try:
                items = _json.loads(item_str)
                if isinstance(items, list):
                    for item in items:
                        product_names.add(item.lower())
            except Exception:
                pass
    except Exception as e:
        log.error(f"Product fetch error: {e}")
        product_names = set()

    # ── LLM extraction ────────────────────────────────────
    extraction_prompt = f"""You are an order query analyzer. Extract information from the user message.

User message: "{state['current_input']}"
User's ordered products: {list(product_names)[:20]}

Extract and return ONLY a JSON object with these fields:
{{
    "order_id": "ORD1234 if mentioned else null",
    "status_filter": "one of [IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, PENDING, DELAYED, RETURNED] or null",
    "product_keyword": "product name from user's orders if mentioned else null",
    "shipping_mode": "Standard Class|First Class|Express|Second Class or null",
    "carrier_filter": "FedEx|Delhivery|Ekart|Bluedart|Xpressbees or null",
    "special_query": "one of [count, cheapest, most_expensive, last_week, last_month, late_risk, upcoming, recent, oldest] or null",
    "city_filter": "city name if mentioned else null",
    "min_price": null,
    "max_price": null,
    "limit": 10,
    "date_filter": "YYYY-MM-DD if a specific date is mentioned else null",
    "month_filter": "month number 1-12 if a month is mentioned else null",
    "year_filter": "4-digit year if a year is mentioned else null"
}}


Rules:
- order_id: extract if user mentions ORD followed by numbers
- status_filter: set for ANY of these patterns:
 'delivered orders', 'what are delivered', 'show delivered', 'orders that are delivered' = DELIVERED
 'pending orders', 'show pending', 'orders that are pending' = PENDING
 'delayed orders', 'show delayed', 'stuck orders' = DELAYED
 'in transit orders', 'on the way orders', 'shipped orders' = IN_TRANSIT
 'out for delivery orders' = OUT_FOR_DELIVERY
 'returned orders' = RETURNED
  DO NOT set status_filter for: 'where is my order', 'track my order', 'what is the status of my order'
- product_keyword: the product/item name ONLY (e.g. "jewellery", "SSD", "laptop", "power bank"). Extract ONLY the noun product name — strip action words like "arrives", "status", "delivery", "tracking", "when", "where", "order". NEVER include carrier names (BlueDart, FedEx, Delhivery, Ekart, Xpressbees, Shadowfax) or shipping modes or status words. Example: "when my jewellery arrives" → product_keyword="jewellery". "count my bluedart orders" → product_keyword=null (bluedart is a carrier, not a product).
- shipping_mode: set if user mentions:
  express/express orders/express delivery = Express
  standard/standard class/standard orders = Standard Class
  first class/first class orders = First Class
  second class = Second Class
  NEVER put shipping mode in special_query or product_keyword
- carrier_filter: fedex/fed ex=FedEx, bluedart/blue dart=Bluedart, ekart/e-kart=Ekart, delhivery=Delhivery, xpressbees=Xpressbees
- special_query: ONLY for these patterns — NOT for status or shipping queries:
  how many/count my orders = count
  cheapest/lowest price = cheapest
  most expensive/costliest = most_expensive
  last week/past week = last_week
  last month/past month = last_month
  late risk/might be late = late_risk
  yet to come/upcoming/not yet delivered/orders to arrive = upcoming
  recently/latest/what did i order = recent
  oldest/earliest = oldest
- min_price: numeric if user says above/over/more than/greater than [amount]
- max_price: numeric if user says below/under/less than/cheaper than [amount]
- EXAMPLES: 'orders below 1000' = max_price=1000, 'orders above 5000' = min_price=5000
- city_filter: city name if mentioned
- limit: if users message has "all" then 20, else 10
- PRIORITY: status_filter and shipping_mode take priority over special_query
- date_filter: ONLY if user mentions a SPECIFIC DAY (e.g. "31-05-2026", "2026-05-31", "May 31 2026", "5th june"), convert to YYYY-MM-DD. Never set this for month-only queries.
- month_filter: if user mentions a month WITHOUT a specific day (e.g. "in May", "june 2026", "orders in june", "june orders", "month 5"), extract as 1-12 integer. Set null if date_filter is set.
- year_filter: if user mentions a year (e.g. "in 2026", "placed in 2025"), extract as 4-digit integer.
- CRITICAL: "june 2026" → month_filter=6, year_filter=2026, date_filter=null. NOT date_filter="2026-06-01".
- CRITICAL: "may 2025" → month_filter=5, year_filter=2025, date_filter=null.
- If a SPECIFIC DAY is given, set date_filter and leave month_filter/year_filter null.

Return ONLY valid JSON. No explanation."""

    log.debug(f"Calling LLM for: {state['current_input']}")

    try:
        response = llm.invoke(extraction_prompt)
        text = response.content.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.replace("json", "").strip()
                if part.startswith("{"):
                    text = part
                    break
        extracted = _json.loads(text)
        log.info(f"LLM extracted: {extracted}")

        usage = response.usage_metadata or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = log_llm_span(
            span_name="validate_input",
            prompt_text=extraction_prompt,
            response_text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=config.LLM_MODEL,
            prompt_name="validate_input",
            prompt_version=1,
            trace_id=state.get("mlflow_trace_id"),
            parent_id=state.get("mlflow_span_id"),
        )

    except Exception as e:
        log.error(f"LLM extraction failed: {e}")
        extracted = {
            "order_id": None,
            "status_filter": None,
            "product_keyword": None,
            "special_query": None,
            "carrier_filter": None,
            "shipping_mode": None,
            "city_filter": None,
            "min_price": None,
            "max_price": None,
            "limit": 10,
        }
        input_tokens = 0
        output_tokens = 0
        cost = 0

    # ── Override limit when user explicitly says "all" ────
    if re.search(r"\ball\b", msg_lower) and re.search(r"\border", msg_lower):
        final_limit = 100
    else:
        final_limit = extracted.get("limit", 10)

    # ── Regex fallback for special_query ─────────────────
    # LLM misses synonyms like "costliest", so catch them here.
    if not extracted.get("special_query"):
        _SQ_PATTERNS = [
            (r"\b(costliest|most\s+expensive|highest\s+(?:price|value|cost)|priciest)\b", "most_expensive"),
            (r"\b(cheapest|lowest\s+(?:price|cost)|most\s+affordable|least\s+expensive)\b", "cheapest"),
            (r"\b(late\s+risk|might\s+be\s+late|at\s+risk|delay\s+risk)\b", "late_risk"),
            (r"\b(upcoming|yet\s+to\s+(?:come|arrive|deliver)|not\s+yet\s+delivered)\b", "upcoming"),
            (r"\b(oldest|earliest|first\s+(?:order|purchase))\b", "oldest"),
        ]
        for _pat, _sq in _SQ_PATTERNS:
            if re.search(_pat, msg_lower):
                extracted["special_query"] = _sq
                break

    # ── Regex fallback for status_filter ─────────────────
    _STATUS_PATTERNS = [
        (r"\bpending\b", "PENDING"),
        (r"\bdelayed\b", "DELAYED"),
        (r"\bdelivered\b", "DELIVERED"),
        (r"\breturned\b", "RETURNED"),
        (r"\bin[\s_-]?transit\b|\bintransit\b", "IN_TRANSIT"),
        (r"\bout[\s_-]?for[\s_-]?delivery\b", "OUT_FOR_DELIVERY"),
        (r"\bcancelled\b", "CANCELLED"),
    ]
    if not extracted.get("status_filter"):
        for pattern, status in _STATUS_PATTERNS:
            if re.search(pattern, msg_lower):
                extracted["status_filter"] = status
                break

    # ── Regex fallback for min_price / max_price ──────────
    if not extracted.get("min_price"):
        m = re.search(
            r"(?:above|over|more\s+than|greater\s+than|minimum|at\s+least)\s+"
            r"(?:rs\.?\s*|₹\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\b",
            msg_lower,
        )
        if m:
            extracted["min_price"] = float(m.group(1).replace(",", ""))

    if not extracted.get("max_price"):
        m = re.search(
            r"(?:below|under|less\s+than|within|upto|up\s+to|cheaper\s+than)\s+"
            r"(?:rs\.?\s*|₹\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\b",
            msg_lower,
        )
        if m:
            extracted["max_price"] = float(m.group(1).replace(",", ""))

    # ── Relative date shortcuts ───────────────────────────────────────
    _today = _date.today()
    if re.search(r"\bthis\s+month\b", msg_lower):
        extracted["month_filter"] = _today.month
        extracted["year_filter"] = _today.year
    elif re.search(r"\blast\s+month\b", msg_lower):
        _first = _today.replace(day=1)
        _prev = _first - _td(days=1)
        extracted["month_filter"] = _prev.month
        extracted["year_filter"] = _prev.year
    elif re.search(r"\bthis\s+year\b", msg_lower):
        extracted["year_filter"] = _today.year
    elif re.search(r"\blast\s+year\b", msg_lower):
        extracted["year_filter"] = _today.year - 1
    elif re.search(r"\btoday\b", msg_lower):
        extracted["date_filter"] = str(_today)
    elif re.search(r"\byesterday\b", msg_lower):
        extracted["date_filter"] = str(_today - _td(days=1))

    # ── Date/month/year — regex-only, LLM values discarded ───────────
    # LLM is unreliable here: it guesses wrong years and defaults to the
    # 1st of the month when only a month name is mentioned. Pure regex is
    # more accurate and consistent.
    _MONTH_NAMES = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    # Preserve relative date values set above; only reset if not already set
    if not extracted.get("date_filter"):
        extracted["date_filter"] = None
    if not extracted.get("month_filter"):
        extracted["month_filter"] = None
    if not extracted.get("year_filter"):
        extracted["year_filter"] = None

    # LLM correction: if the LLM set date_filter to "YYYY-MM-01" but the user only
    # mentioned a month name + year (no specific day), it defaulted to the 1st.
    # Convert to month_filter + year_filter so all orders in that month are returned.
    _df = extracted.get("date_filter") or ""
    if _df and _df.endswith("-01"):
        _has_day_in_msg = bool(
            re.search(r"\b(?:1st|01|first)\b", msg_lower)
            or re.search(
                r"\b1\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b",
                msg_lower,
            )
            or re.search(
                r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+1\b",
                msg_lower,
            )
        )
        _has_month_name = any(re.search(r"\b" + n + r"\b", msg_lower) for n in _MONTH_NAMES)
        if _has_month_name and not _has_day_in_msg:
            # User said "may 2026" not "1 may 2026" — treat as full-month query
            try:
                _yr, _mo, _ = _df.split("-")
                extracted["date_filter"] = None
                extracted["month_filter"] = int(_mo)
                extracted["year_filter"] = int(_yr)
            except ValueError:
                pass

    # 1. Specific date patterns — set date_filter only
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", msg_lower)
    if m:
        extracted["date_filter"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    else:
        m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", msg_lower)
        if m:
            extracted["date_filter"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            # "31 May 2026" or "May 31 2026" or "May 31, 2026"
            _mon_pat = "|".join(_MONTH_NAMES)
            m = re.search(r"\b(\d{1,2})\s+(" + _mon_pat + r")\s+(\d{4})\b", msg_lower) or re.search(
                r"\b(" + _mon_pat + r")\s+(\d{1,2})[,\s]+(\d{4})\b", msg_lower
            )
            if m:
                g = m.groups()
                if g[0].isdigit():
                    day, mon, yr = int(g[0]), _MONTH_NAMES[g[1]], int(g[2])
                else:
                    day, mon, yr = int(g[1]), _MONTH_NAMES[g[0]], int(g[2])
                extracted["date_filter"] = f"{yr}-{mon:02d}-{day:02d}"

    # 2. Month name (only if no specific date found and not already set by relative date)
    if not extracted["date_filter"] and not extracted["month_filter"]:
        for name, num in _MONTH_NAMES.items():
            if re.search(r"\b" + name + r"\b", msg_lower):
                extracted["month_filter"] = num
                break

    # 3. Year (only if no specific date found and not already set by relative date)
    if not extracted["date_filter"] and not extracted["year_filter"]:
        m = re.search(r"\b(20\d{2})\b", msg_lower)
        extracted["year_filter"] = int(m.group(1)) if m else None

    # ── Date takes priority over time-based special queries ───────────
    # "orders in June 2026" must not fall into special_query="recent"
    # "orders this month" must not fall into special_query="recent"
    _TIME_SQ = {"recent", "last_week", "last_month", "oldest"}
    if extracted.get("special_query") in _TIME_SQ and (
        extracted.get("date_filter") or extracted.get("month_filter") or extracted.get("year_filter")
    ):
        extracted["special_query"] = None

    # ── Sanitise LLM product_keyword ─────────────────────
    # Clear product_keyword if it's only time/stop words (e.g. LLM returns
    # "orders in" for "what are my orders in june 2026").
    _TIME_STOP = {
        "in",
        "on",
        "at",
        "for",
        "from",
        "by",
        "of",
        "the",
        "my",
        "i",
        "orders",
        "order",
        "all",
        "recent",
        "what",
        "are",
        "show",
        "give",
        # price prepositions — must never become product_keyword
        "above",
        "below",
        "under",
        "over",
        "within",
        "upto",
        # status words — must never become product_keyword
        "pending",
        "delivered",
        "delayed",
        "returned",
        "transit",
        "cancelled",
        "intransit",
        # month names
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    }
    _pk = extracted.get("product_keyword") or ""
    # Strip trailing noise words from product_keyword ("sunglasses orders" → "sunglasses")
    _TRAILING_NOISE = {"orders", "order", "items", "item", "products", "product", "purchases"}
    if _pk:
        _pk_words = _pk.strip().split()
        while _pk_words and _pk_words[-1].lower() in _TRAILING_NOISE:
            _pk_words.pop()
        _pk = " ".join(_pk_words)
        extracted["product_keyword"] = _pk or None
    # Clear entirely if only time/stop words remain
    if _pk and all(w.lower() in _TIME_STOP or w.isdigit() for w in _pk.split()):
        extracted["product_keyword"] = None

    # ── Regex fallback for product_keyword ───────────────
    # Catches cases where LLM skips product_keyword because the item
    # isn't in the user's orders list (e.g. "how many SSD orders").
    if not extracted.get("product_keyword"):
        _IGNORE = {
            "my",
            "the",
            "all",
            "total",
            "of",
            "do",
            "i",
            "have",
            "how",
            "many",
            "any",
            "order",
            "orders",
            "there",
            "are",
            # status words — must never become product_keyword
            "pending",
            "delivered",
            "delayed",
            "returned",
            "transit",
            "in_transit",
            "out_for_delivery",
            "cancelled",
        }
        m = re.search(r"(?:how\s+many|count\s+of|number\s+of|any)\s+(\w+(?:[\s-]\w+)?)\s+order", msg_lower)
        if m:
            candidate = m.group(1).strip()
            if candidate not in _IGNORE:
                extracted["product_keyword"] = candidate

        # "where is my mouse", "where is my keyboard order", "track my webcam"
        if not extracted.get("product_keyword"):
            m = re.search(
                r"(?:where\s+is\s+my|where\s+is\s+the|track\s+my|status\s+of\s+my|my)\s+(\w+(?:\s+\w+)?)"
                r"(?:\s+order)?",
                msg_lower,
            )
            if m:
                candidate = m.group(1).strip()
                if candidate not in _IGNORE and len(candidate) > 2:
                    extracted["product_keyword"] = candidate

        # "when i ordered headphones", "what are the dates i ordered headphones"
        if not extracted.get("product_keyword"):
            m = re.search(r"\bordered?\s+(\w+(?:\s+\w+)?)\s*$", msg_lower)
            if m:
                candidate = m.group(1).strip()
                if candidate not in _IGNORE and len(candidate) > 2:
                    extracted["product_keyword"] = candidate

    # ── Compound product name normalization ──────────────
    _COMPOUND_NORM = {
        "smartwatch": "smart watch",
        "smarttv": "smart tv",
        "powerbank": "power bank",
        "earbud": "earbuds",
    }
    _raw_pk = extracted.get("product_keyword") or ""
    if _raw_pk.lower() in _COMPOUND_NORM:
        extracted["product_keyword"] = _COMPOUND_NORM[_raw_pk.lower()]

    # ── Final sanitise pass (catches regex-set values too) ───
    _final_pk = extracted.get("product_keyword") or ""
    if _final_pk:
        # Strip trailing noise words
        _pk_words = _final_pk.split()
        while _pk_words and _pk_words[-1].lower() in _TRAILING_NOISE:
            _pk_words.pop()
        _final_pk = " ".join(_pk_words)
        # Clear if only stop/time words remain
        if not _final_pk or all(w.lower() in _TIME_STOP or w.isdigit() for w in _final_pk.split()):
            _final_pk = None
        extracted["product_keyword"] = _final_pk

    # ── Always return all filters — NO DB QUERIES ─────────
    return {
        **state,
        "order_id": extracted.get("order_id"),
        "status_filter": extracted.get("status_filter"),
        "product_keyword": extracted.get("product_keyword"),
        "special_query": extracted.get("special_query"),
        "carrier_filter": extracted.get("carrier_filter"),
        "shipping_mode": extracted.get("shipping_mode"),
        "city_filter": extracted.get("city_filter"),
        "min_price": extracted.get("min_price"),
        "max_price": extracted.get("max_price"),
        "query_limit": final_limit,
        "date_filter": extracted.get("date_filter"),
        "month_filter": extracted.get("month_filter"),
        "year_filter": extracted.get("year_filter"),
        "total_tokens": state.get("total_tokens", 0) + input_tokens + output_tokens,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + cost,
    }


# ─────────────────────────────────────────────
# NODE 2 — fetch_order_data (uses ToolNode)
# ─────────────────────────────────────────────


def fetch_order_data(state: AgentState) -> AgentState:
    """Calls fetch_orders via ToolNode then formats the response from returned data."""
    log = get_log(state["request_id"], "order_agent", "fetch_order_data")
    log.info("Tool called: fetch_order_data via ToolNode")

    user_id = state.get("user_id")
    order_id = state.get("order_id")
    special_query = state.get("special_query")
    status_filter = state.get("status_filter")
    product_keyword = state.get("product_keyword")
    carrier_filter = state.get("carrier_filter")
    shipping_mode = state.get("shipping_mode")
    city_filter = state.get("city_filter")
    min_price = state.get("min_price")
    max_price = state.get("max_price")
    limit = state.get("query_limit", 10)
    date_filter = state.get("date_filter")
    month_filter = state.get("month_filter")
    year_filter = state.get("year_filter")
    msg_lower = state["current_input"].lower()

    log.info(
        f"Query params — order_id={order_id} special={special_query} "
        f"status={status_filter} product={product_keyword} carrier={carrier_filter} limit={limit}"
    )

    # ── Build and invoke ToolNode ─────────────────────────────
    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "fetch_orders",
                "args": {
                    "user_id": user_id,
                    "order_id": order_id,
                    "status_filter": status_filter,
                    "product_keyword": product_keyword,
                    "carrier_filter": carrier_filter,
                    "shipping_mode": shipping_mode,
                    "city_filter": city_filter,
                    "min_price": min_price,
                    "max_price": max_price,
                    "limit": limit,
                    "date_filter": date_filter,
                    "month_filter": month_filter,
                    "year_filter": year_filter,
                    "special_query": special_query,
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )

    with mlflow.start_span(name="fetch_order_data", span_type="TOOL") as span:
        span.set_inputs({"order_id": order_id, "special_query": special_query, "limit": limit})
        tool_result = order_tool_node.invoke({"messages": [ai_msg]})
        data = _json.loads(tool_result["messages"][-1].content)
        span.set_outputs({"type": data.get("type"), "count": len(data.get("orders", []))})

    log_tool_span(
        "fetch_order_data",
        "postgresql_orders_table",
        {"order_id": order_id, "special_query": special_query},
        {"type": data.get("type"), "result_count": len(data.get("orders", []))},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    # ── Format response from tool data ────────────────────────
    result_type = data.get("type")

    if result_type == "not_found":
        return {
            **state,
            "order_data": None,
            "response": f"Sorry, I could not find order #{order_id}. Please check the order ID and try again.",
        }

    if result_type == "unauthorized":
        return {**state, "order_data": None, "response": f"Sorry, order #{order_id} does not belong to your account."}

    if result_type == "single_order":
        return {**state, "order_data": data["single_order"]}

    if result_type == "count":
        breakdown_lines = "\n".join([f"  • {b['status']}: {b['count']}" for b in data["breakdown"]])
        filters = data.get("filters", {})
        filter_parts = [
            v
            for v in [
                filters.get("product_keyword"),
                filters.get("carrier_filter"),
                filters.get("status_filter"),
                filters.get("shipping_mode"),
            ]
            if v
        ]
        filter_desc = " " + " ".join(filter_parts) if filter_parts else ""
        suffix = "in total" if not filter_parts else ""
        return {
            **state,
            "order_data": None,
            "response": f"You have {data['total']}{filter_desc} orders{' ' + suffix if suffix else ''}.\n\nBreakdown:\n{breakdown_lines}",
        }

    if result_type in ("cheapest", "most_expensive"):
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "No orders found for that filter."}
        label = "cheapest" if result_type == "cheapest" else "most expensive"
        lines = "\n".join(
            [f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders]
        )
        return {
            **state,
            "order_data": None,
            "response": f"Here are your {label} orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details.",
        }

    if result_type == "last_week":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders from the last week."}
        lines = "\n".join(
            [
                f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}"
                for o in orders
            ]
        )
        return {
            **state,
            "order_data": None,
            "response": f"Here are your orders from the last week:\n\n{lines}\n\nReply with an Order ID to get full tracking details.",
        }

    if result_type == "last_month":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders from the last month."}
        lines = "\n".join(
            [
                f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}"
                for o in orders
            ]
        )
        return {
            **state,
            "order_data": None,
            "response": f"Here are your orders from the last month:\n\n{lines}\n\nReply with an Order ID to get full tracking details.",
        }

    if result_type == "late_risk":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "None of your orders have a late delivery risk."}
        lines = "\n".join(
            [
                f"• {o['order_id']} — {o['status']} via {o['carrier']} (Delivery: {o['estimated_delivery']}) — Items: {o['items']}"
                for o in orders
            ]
        )
        return {
            **state,
            "order_data": None,
            "response": f"These orders have a late delivery risk:\n\n{lines}\n\nReply with an Order ID for full details.",
        }

    if result_type == "upcoming":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "All your orders have been delivered."}
        grouped = group_orders_by_status(orders)
        return {
            **state,
            "order_data": None,
            "response": f"Here are your upcoming orders:\n\n{grouped}\n\nReply with an Order ID for full details.",
        }

    if result_type == "recent":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders in our system yet."}
        lines = "\n".join(
            [
                f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}"
                for o in orders
            ]
        )
        return {
            **state,
            "order_data": None,
            "response": f"Here are your most recent orders:\n\n{lines}\n\nReply with an Order ID for full details.",
        }

    if result_type == "oldest":
        orders = data.get("orders", [])
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders in our system yet."}
        lines = "\n".join(
            [
                f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}"
                for o in orders
            ]
        )
        return {
            **state,
            "order_data": None,
            "response": f"Here are your oldest orders:\n\n{lines}\n\nReply with an Order ID for full details.",
        }

    # ── General filter result ─────────────────────────────────
    orders = data.get("orders", [])
    filters = data.get("filters", {})
    if not orders:
        pk = filters.get("product_keyword")
        sm = filters.get("shipping_mode")
        cf = filters.get("carrier_filter")
        cy = filters.get("city_filter")
        mn = filters.get("min_price")
        mx = filters.get("max_price")
        df = filters.get("date_filter")
        mf = filters.get("month_filter")
        yf = filters.get("year_filter")
        if sm:
            return {**state, "order_data": None, "response": f"I could not find any {sm} orders in your account."}
        elif pk:
            return {
                **state,
                "order_data": None,
                "response": f"I could not find any orders containing '{pk}'. Would you like to see all your recent orders instead?",
            }
        elif cf:
            return {
                **state,
                "order_data": None,
                "response": f"I could not find any orders shipped via '{cf}' in your account.",
            }
        elif cy:
            return {
                **state,
                "order_data": None,
                "response": f"I could not find any orders from '{cy}' in your account.",
            }
        elif mn or mx:
            return {**state, "order_data": None, "response": "I could not find any orders matching that price range."}
        elif df:
            return {**state, "order_data": None, "response": f"You have no orders placed on {df}."}
        elif mf and yf:
            return {
                **state,
                "order_data": None,
                "response": f"You have no orders placed in {calendar.month_name[mf]} {yf}.",
            }
        elif mf:
            return {**state, "order_data": None, "response": f"You have no orders placed in {calendar.month_name[mf]}."}
        elif yf:
            return {**state, "order_data": None, "response": f"You have no orders placed in {yf}."}
        return {**state, "order_data": None, "response": "You have no orders in our system yet."}

    # Single arrival-keyword match → return full order data
    arrival_keywords = ["when arrives", "when will", "when does", "when is", "arrives", "arrival"]
    if len(orders) == 1 and any(kw in msg_lower for kw in arrival_keywords):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM orders WHERE order_id = %s", [orders[0]["order_id"]])
                row = cur.fetchone()
                if row:
                    return {**state, "order_data": dict(row)}

    grouped = group_orders_by_status(orders)
    return {
        **state,
        "order_data": None,
        "response": f"Here are your matching orders:\n\n{grouped}\n\nWhich order would you like to track? Reply with the Order ID (e.g. ORD2001).",
    }


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
# NODE 4 — generate_response (LLM 2)
# ─────────────────────────────────────────────


def generate_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "generate_response")
    log.info("LLM called")

    summary = state.get("conversation_summary") or ""
    recent = str(state.get("messages", []))
    history_context = f"{summary}\nRecent: {recent}".strip()

    tracking = state.get("tracking_info") or {}
    raw_events = tracking.get("events") or []
    events_text = (
        "\n".join(f"  • {str(e.get('time', ''))[:16].replace('T', ' ')} — {e.get('status', '')}" for e in raw_events)
        if raw_events
        else "No events available."
    )

    prompt = f"""You are a helpful customer service assistant for an e-commerce platform.

Order data: {str(state.get('order_data', {}))}
Tracking info: {str(tracking)}
Customer asked: {state['current_input']}
Conversation history: {history_context}

Write a clear friendly response covering: customer name, current status, carrier name,
tracking number, current city/location (from tracking_info current_location), and ETA.
Keep this part to 2-3 sentences.

Then add a section exactly like this:

**Current Location:** <current_location from tracking_info>

**Tracking Timeline:**
{events_text}

Sign off as: Customer Support Team"""

    response = llm.invoke(prompt)
    usage = response.usage_metadata
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cost = log_llm_span(
        span_name="generate_response",
        prompt_text=prompt,
        response_text=response.content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=config.LLM_MODEL,
        prompt_name="response_generation_prompt",
        prompt_version=config.RESPONSE_GENERATION_PROMPT_VERSION,
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info("Response generated")
    return {
        **state,
        "response": response.content,
        "total_tokens": state["total_tokens"] + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


# ─────────────────────────────────────────────
# NODE 5 — save_to_db
# ─────────────────────────────────────────────


def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "save_to_db")
    log.info("Saving response to DB")
    with mlflow.start_span(name="save_to_db", span_type="TOOL") as span:
        span.set_inputs({"session_id": state["session_id"], "role": "assistant"})
        save_message(
            session_id=state["session_id"],
            role="assistant",
            content=state["response"],
            agent_name="order_agent",
            token_usage={
                "total_tokens": state["total_tokens"],
                "total_cost_usd": state["total_cost_usd"],
            },
            mlflow_run_id=state.get("mlflow_run_id"),
        )
        span.set_outputs({"status": "saved"})
    log.info("Response saved")
    return state


# ─────────────────────────────────────────────
# EDGES
# ─────────────────────────────────────────────


def validate_input_edge(state: AgentState) -> str:
    if state.get("response"):
        return "error_response"  # guest blocked
    return "fetch_order_data"  # always — handles everything


def order_found_edge(state: AgentState) -> str:
    if state.get("order_data"):
        return "shipment_tracking"  # single order — track it
    if state.get("response"):
        return "save_to_db"  # listing/special — save directly
    return "error_response"  # nothing found


# ─────────────────────────────────────────────
# BUILD ORDER AGENT GRAPH
# ─────────────────────────────────────────────


def build_order_agent():
    graph = StateGraph(AgentState)

    graph.add_node("validate_input", validate_input)
    graph.add_node("fetch_order_data", fetch_order_data)
    graph.add_node("shipment_tracking", build_shipment_subgraph())
    graph.add_node("generate_response", generate_response)
    graph.add_node("save_to_db", save_to_db)
    graph.add_node("error_response", error_response)

    graph.set_entry_point("validate_input")

    graph.add_conditional_edges(
        "validate_input",
        validate_input_edge,
        {
            "fetch_order_data": "fetch_order_data",
            "error_response": "error_response",
        },
    )

    graph.add_conditional_edges(
        "fetch_order_data",
        order_found_edge,
        {
            "shipment_tracking": "shipment_tracking",
            "save_to_db": "save_to_db",
            "error_response": "error_response",
        },
    )

    graph.add_edge("shipment_tracking", "generate_response")
    graph.add_edge("generate_response", "save_to_db")
    graph.add_edge("save_to_db", END)
    graph.add_edge("error_response", END)

    return graph.compile()


order_agent = build_order_agent()


# ─────────────────────────────────────────────
# TEST BLOCK
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    state = empty_state(
        session_id=session_id,
        user_id="test-user",
        request_id="test-req-001",
        messages=[],
        current_input="where is my order ORD3005",
    )

    result = order_agent.invoke(state)
    print(f"\n=== RESULT ===")
    print(f"Order ID:  {result['order_id']}")
    print(f"Response:  {result['response']}")
    print(f"Tokens:    {result['total_tokens']}")
    print(f"Cost:      ${result['total_cost_usd']}")
