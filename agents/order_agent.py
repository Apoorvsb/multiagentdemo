# import re
# import mlflow
# import psycopg2.extras
# from database import get_conn
# import json
# from langchain_groq import ChatGroq
# from state import AgentState
# from config import config
# from logger import get_log
# from mlflow_helpers import log_llm_span, log_tool_span
# from agents.shipment_subgraph import build_shipment_subgraph
# from langgraph.graph import StateGraph, END
# from database import save_message

# from mlflow_helpers import calculate_cost, log_tool_span, log_llm_span

# import state

# llm = ChatGroq(
#     model=config.LLM_MODEL,
#     temperature=0,
#     api_key=config.GROQ_API_KEY
# )

# print(" CONFIG MODEL =", config.LLM_MODEL)

# # ─────────────────────────────────────────────
# # NODE 1 — validate_input (LLM ONLY)
# # ─────────────────────────────────────────────

# def validate_input(state: AgentState) -> AgentState:
#     log = get_log(state["request_id"], "order_agent", "validate_input")
#     log.info("Node entered")

#     # ── Block guest users ─────────────────────────────────
#     user_id = state.get("user_id", "")
#     if user_id.endswith("@guest.com"):
#         return {
#             **state,
#             "order_id": None,
#             "response": "Guest users cannot access order information. Please sign up or log in to track your orders."
#         }

#     msg_lower = state["current_input"].lower()

#     # ── Check explicit order ID first (no LLM needed) ────
#     msg_upper = state["current_input"].upper()
#     match = re.search(r'(ORD\d+)', msg_upper)
#     if match:
#         log.info(f"Explicit order ID found: {match.group(1)}")
#         return {**state, "order_id": match.group(1)}

#     # ── Check follow-up from history (no LLM needed) ─────
#     followup_keywords = [
#         "when will", "when does", "when it", "when was", "when did",
#         "where is it", "will it arrive", "eta", "how long", "update",
#         "delivery date", "tracking number", "current status",
#         "what happened", "latest update", "track it", "has it", "did it",
#         "what is the status", "what's the status", "status of",
#         "tell me the status", "give me the status", "any update",
#         "where is it now", "tell me more",
#         "more details", "more info", "show details", "give me details",
#         "is it delivered", "has it arrived",
#         "what is the order", "order id", "order number",
#         "give me the order", "what is the id", "tell me the order",
#     ]
#     is_followup = any(kw in msg_lower for kw in followup_keywords)

#     msg_words = [w for w in msg_lower.split() if len(w) > 3]
#     stop_words = {"what", "when", "where", "show", "list", "give", "tell", "find", "order", "orders", "will", "does", "have", "that", "this", "your", "mine"}
#     content_words = [w for w in msg_words if w not in stop_words]
#     has_product_mention = len(content_words) > 0 and not any(kw in msg_lower for kw in followup_keywords)

#     if is_followup and not has_product_mention and state.get("messages"):
#         for msg_item in reversed(state["messages"][-6:]):
#             content = msg_item.get("content", "").upper()
#             prev_match = re.search(r'(ORD\d+)', content)
#             if prev_match:
#                 order_id = prev_match.group(1)
#                 log.info(f"Follow-up detected — reusing order_id={order_id}")
#                 return {**state, "order_id": order_id}

#     # ── LLM extraction ────────────────────────────────────
#     import json as _json

#     # Fetch product names for LLM context only (NOT for DB query)
#     try:
#         with get_conn() as conn:
#             with conn.cursor() as cur:
#                 cur.execute(
#                     "SELECT DISTINCT items::text FROM orders WHERE user_id = %s",
#                     [user_id]
#                 )
#                 all_items = [row[0] for row in cur.fetchall()]
#         product_names = set()
#         for item_str in all_items:
#             try:
#                 items = _json.loads(item_str)
#                 if isinstance(items, list):
#                     for item in items:
#                         product_names.add(item.lower())
#             except:
#                 pass
#     except Exception as e:
#         log.error(f"Product fetch error: {e}")
#         product_names = set()

#     extraction_prompt = f"""You are an order query analyzer. Extract information from the user message.

# User message: "{state['current_input']}"
# User's ordered products: {list(product_names)[:20]}

# Extract and return ONLY a JSON object with these fields:
# {{
#     "order_id": "ORD1234 if mentioned else null",
#     "status_filter": "one of [IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, PENDING, DELAYED, RETURNED] or null",
#     "product_keyword": "product name from user's orders if mentioned else null",
#     "shipping_mode": "Standard Class|First Class|Express|Second Class or null",
#     "carrier_filter": "FedEx|Delhivery|Ekart|Bluedart|Xpressbees or null",
#     "special_query": "one of [count, cheapest, most_expensive, last_week, last_month, late_risk, upcoming, recent, oldest] or null",
#     "city_filter": "city name if mentioned else null",
#     "min_price": null,
#     "max_price": null,
#     "limit": 10
# }}

# Rules:
# - order_id: extract if user mentions ORD followed by numbers
# - status_filter: on the way=IN_TRANSIT, stuck=DELAYED, arrived=DELIVERED, not shipped=PENDING, being delivered=OUT_FOR_DELIVERY. ONLY set if user explicitly mentions a status
# - product_keyword: any product or item name the user mentions when asking about their orders (e.g. "SSD", "laptop", "keyboard", "webcam"). Extract it even if it does not appear in the ordered products list above — the user may be searching for it. NEVER set for shipping modes, carriers, or status words
# - shipping_mode: standard/standard orders=Standard Class, first class=First Class, express=Express, second class=Second Class
# - carrier_filter: fedex/fed ex=FedEx, bluedart/blue dart=Bluedart, ekart/e-kart=Ekart, delhivery=Delhivery, xpressbees=Xpressbees
# - special_query: how many/count my orders=count, cheapest=cheapest, most expensive=most_expensive, last week=last_week, last month=last_month, late risk=late_risk, yet to come/not delivered/upcoming=upcoming, recently/latest=recent, oldest/earliest=oldest
# - min_price: numeric if user says above/over/more than [amount]
# - max_price: numeric if user says below/under/less than [amount]
# - city_filter: city name if mentioned
# - limit: 20 if user says 'all', else 10
# - IMPORTANT: yet to be delivered = ALL undelivered orders, use special_query=upcoming not status_filter=PENDING

# Return ONLY valid JSON. No explanation."""

#     print(f"[DEBUG VALIDATE] Calling LLM for: {state['current_input']}")

#     try:
#         response = llm.invoke(extraction_prompt)
#         text = response.content.strip()
#         if "```" in text:
#             parts = text.split("```")
#             for part in parts:
#                 part = part.replace("json", "").strip()
#                 if part.startswith("{"):
#                     text = part
#                     break
#         extracted = _json.loads(text)
#         log.info(f"LLM extracted: {extracted}")

#         usage         = response.usage_metadata or {}
#         input_tokens  = usage.get("input_tokens",  0)
#         output_tokens = usage.get("output_tokens", 0)
#         cost = log_llm_span(
#             span_name     = "validate_input",
#             prompt_text   = extraction_prompt,
#             response_text = text,
#             input_tokens  = input_tokens,
#             output_tokens = output_tokens,
#             model         = config.LLM_MODEL,
#             prompt_name   = "validate_input",
#             prompt_version= 1,
#             trace_id      = state.get("mlflow_trace_id"),
#             parent_id     = state.get("mlflow_span_id"),
#         )

#     except Exception as e:
#         log.error(f"LLM extraction failed: {e}")
#         extracted = {
#             "order_id": None, "status_filter": None, "product_keyword": None,
#             "special_query": None, "carrier_filter": None, "shipping_mode": None,
#             "city_filter": None, "min_price": None, "max_price": None, "limit": 10
#         }
#         input_tokens  = 0
#         output_tokens = 0
#         cost = 0

#     # ── Return filters in state — NO DB QUERIES ───────────
#     return {
#         **state,
#         "order_id":        extracted.get("order_id"),
#         "status_filter":   extracted.get("status_filter"),
#         "product_keyword": extracted.get("product_keyword"),
#         "special_query":   extracted.get("special_query"),
#         "carrier_filter":  extracted.get("carrier_filter"),
#         "shipping_mode":   extracted.get("shipping_mode"),
#         "city_filter":     extracted.get("city_filter"),
#         "min_price":       extracted.get("min_price"),
#         "max_price":       extracted.get("max_price"),
#         "query_limit":     extracted.get("limit", 10),
#         "total_tokens":    state.get("total_tokens", 0) + input_tokens + output_tokens,
#         "total_cost_usd":  state.get("total_cost_usd", 0.0) + cost,
#     }


# # ─────────────────────────────────────────────
# # NODE 2 — fetch_order_listing (NEW TOOL NODE)
# # ─────────────────────────────────────────────

# def fetch_order_listing(state: AgentState) -> AgentState:
#     log = get_log(state["request_id"], "order_agent", "fetch_order_listing")
#     log.info("Tool called: fetch_order_listing")

#     user_id         = state.get("user_id")
#     special_query   = state.get("special_query")
#     status_filter   = state.get("status_filter")
#     product_keyword = state.get("product_keyword")
#     carrier_filter  = state.get("carrier_filter")
#     shipping_mode   = state.get("shipping_mode")
#     city_filter     = state.get("city_filter")
#     min_price       = state.get("min_price")
#     max_price       = state.get("max_price")
#     limit           = state.get("query_limit", 10)
#     msg_lower       = state["current_input"].lower()

#     log_tool_span(
#         "fetch_order_listing",
#         "postgresql_orders_table",
#         {"special_query": special_query, "status_filter": status_filter,
#          "product_keyword": product_keyword, "carrier_filter": carrier_filter},
#         {},
#         trace_id=state.get("mlflow_trace_id"),
#         parent_id=state.get("mlflow_span_id"),
#     )

#     # ── Special queries ───────────────────────────────────
#     if special_query == "count":
#         with get_conn() as conn:
#             with conn.cursor() as cur:
#                 cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", [user_id])
#                 total = cur.fetchone()[0]
#                 cur.execute(
#                     "SELECT status, COUNT(*) FROM orders WHERE user_id = %s GROUP BY status ORDER BY COUNT(*) DESC",
#                     [user_id]
#                 )
#                 breakdown = cur.fetchall()
#         breakdown_lines = "\n".join([f"  • {s}: {c}" for s, c in breakdown])
#         return {**state, "response": f"You have {total} orders in total.\n\nBreakdown:\n{breakdown_lines}"}

#     elif special_query == "cheapest":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer ASC LIMIT 5",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
#         return {**state, "response": f"Here are your cheapest orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

#     elif special_query == "most_expensive":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer DESC LIMIT 5",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
#         return {**state, "response": f"Here are your most expensive orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

#     elif special_query == "last_week":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY order_date DESC LIMIT 10",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "You have no orders from the last week."}
#         lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
#         return {**state, "response": f"Here are your orders from the last week:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

#     elif special_query == "last_month":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '30 days' ORDER BY order_date DESC LIMIT 10",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "You have no orders from the last month."}
#         lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
#         return {**state, "response": f"Here are your orders from the last month:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

#     elif special_query == "late_risk":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items FROM orders WHERE user_id = %s AND late_delivery_risk = 1 AND status NOT IN ('DELIVERED', 'RETURNED') ORDER BY order_date DESC LIMIT 10",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "None of your orders have a late delivery risk."}
#         lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Delivery: {o['estimated_delivery']}) — Items: {o['items']}" for o in orders])
#         return {**state, "response": f"These orders have a late delivery risk:\n\n{lines}\n\nReply with an Order ID for full details."}

#     elif special_query == "upcoming":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items FROM orders WHERE user_id = %s AND status NOT IN ('DELIVERED', 'RETURNED') ORDER BY order_date DESC LIMIT 10",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "All your orders have been delivered."}
#         status_order = ["DELAYED", "PENDING", "IN_TRANSIT", "OUT_FOR_DELIVERY"]
#         grouped = {}
#         for o in orders:
#             s = o["status"]
#             if s not in grouped:
#                 grouped[s] = []
#             grouped[s].append(o)
#         emoji_map = {"DELAYED": "🔴", "PENDING": "🟡", "IN_TRANSIT": "🚚", "OUT_FOR_DELIVERY": "📦"}
#         sections = []
#         for s in status_order:
#             if s in grouped:
#                 section_lines = "\n".join([f"  • {o['order_id']} — via {o['carrier']} (Delivery: {o['estimated_delivery']}) — Items: {o['items']}" for o in grouped[s]])
#                 sections.append(f"{emoji_map.get(s, '•')} **{s.replace('_', ' ')}**\n{section_lines}")
#         return {**state, "response": f"Here are your upcoming orders:\n\n{chr(10).join(sections)}\n\nReply with an Order ID for full details."}

#     elif special_query == "recent":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s ORDER BY order_date DESC LIMIT 5",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "You have no orders in our system yet."}
#         lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
#         return {**state, "response": f"Here are your most recent orders:\n\n{lines}\n\nReply with an Order ID for full details."}

#     elif special_query == "oldest":
#         with get_conn() as conn:
#             with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#                 cur.execute(
#                     "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s ORDER BY order_date ASC LIMIT 5",
#                     [user_id]
#                 )
#                 orders = [dict(r) for r in cur.fetchall()]
#         if not orders:
#             return {**state, "response": "You have no orders in our system yet."}
#         lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
#         return {**state, "response": f"Here are your oldest orders:\n\n{lines}\n\nReply with an Order ID for full details."}

#     # ── Filter queries ────────────────────────────────────
#     conditions = ["user_id = %s"]
#     params     = [user_id]

#     if status_filter:
#         conditions.append("status = %s")
#         params.append(status_filter)
#     if product_keyword:
#         conditions.append("items::text ILIKE %s")
#         params.append(f"%{product_keyword}%")
#     if carrier_filter:
#         conditions.append("carrier ILIKE %s")
#         params.append(f"%{carrier_filter}%")
#     if shipping_mode:
#         conditions.append("shipping_mode ILIKE %s")
#         params.append(f"%{shipping_mode}%")
#     if city_filter:
#         conditions.append("order_city ILIKE %s")
#         params.append(f"%{city_filter}%")
#     if min_price:
#         conditions.append("sales_per_customer >= %s")
#         params.append(float(min_price))
#     if max_price:
#         conditions.append("sales_per_customer <= %s")
#         params.append(float(max_price))

#     where = " AND ".join(conditions)
#     with get_conn() as conn:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(
#                 f"""SELECT order_id, status, carrier, estimated_delivery, items
#                     FROM orders WHERE {where}
#                     ORDER BY order_date DESC LIMIT {limit}""",
#                 params
#             )
#             orders = [dict(r) for r in cur.fetchall()]

#     # Single match + arrival question → pass order_id to fetch_order_data
#     arrival_keywords = ["when arrives", "when will", "when does", "when is", "arrives", "arrival", "deliver when"]
#     if len(orders) == 1 and any(kw in msg_lower for kw in arrival_keywords):
#         return {**state, "order_id": orders[0]["order_id"]}

#     if not orders:
#         if shipping_mode:
#             return {**state, "response": f"I could not find any {shipping_mode} orders in your account."}
#         elif product_keyword:
#             return {**state, "response": f"I could not find any orders containing '{product_keyword}'. Would you like to see all your recent orders instead?"}
#         elif carrier_filter:
#             return {**state, "response": f"I could not find any orders shipped via '{carrier_filter}' in your account."}
#         elif city_filter:
#             return {**state, "response": f"I could not find any orders from '{city_filter}' in your account."}
#         elif min_price or max_price:
#             return {**state, "response": "I could not find any orders matching that price range."}
#         else:
#             return {**state, "response": "You have no orders in our system yet."}

#     # Group and sort by status
#     status_order = ["DELAYED", "PENDING", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"]
#     grouped = {}
#     for o in orders:
#         s = o["status"]
#         if s not in grouped:
#             grouped[s] = []
#         grouped[s].append(o)

#     sections = []
#     for status in status_order:
#         if status in grouped:
#             section_lines = "\n".join([
#                 f"  • {o['order_id']} — via {o['carrier']} "
#                 f"(Delivery: {o['estimated_delivery']}) — Items: {o['items']}"
#                 for o in grouped[status]
#             ])
#             emoji = {
#                 "DELAYED":          "🔴",
#                 "PENDING":          "🟡",
#                 "IN_TRANSIT":       "🚚",
#                 "OUT_FOR_DELIVERY": "📦",
#                 "DELIVERED":        "✅",
#                 "RETURNED":         "↩️",
#             }.get(status, "•")
#             sections.append(f"{emoji} **{status.replace('_', ' ')}**\n{section_lines}")

#     for status, items in grouped.items():
#         if status not in status_order:
#             section_lines = "\n".join([
#                 f"  • {o['order_id']} — via {o['carrier']} "
#                 f"(Delivery: {o['estimated_delivery']}) — Items: {o['items']}"
#                 for o in items
#             ])
#             sections.append(f"• **{status}**\n{section_lines}")

#     lines = "\n\n".join(sections)
#     return {
#         **state,
#         "response": f"Here are your matching orders:\n\n{lines}\n\nWhich order would you like to track? Reply with the Order ID (e.g. ORD2001)."
#     }


# # ─────────────────────────────────────────────
# # NODE 3 — fetch_order_data (UNCHANGED)
# # ─────────────────────────────────────────────

# def fetch_order_data(state: AgentState) -> AgentState:
#     print(f"DEBUG trace_id: {state.get('mlflow_trace_id')}")
#     print(f"DEBUG span_id:  {state.get('mlflow_span_id')}")
#     log = get_log(state["request_id"], "order_agent", "fetch_order_data")
#     log.info("Tool called: fetch_order_data")
#     order_id = state.get("order_id")
#     user_id  = state.get("user_id")

#     with get_conn() as conn:
#         with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#             cur.execute(
#                 "SELECT * FROM orders WHERE order_id = %s",
#                 [order_id]
#             )
#             row   = cur.fetchone()
#             order = dict(row) if row else None

#     if not order:
#         log.warning(f"Order not found: {order_id}")
#         log_tool_span(
#             "fetch_order_data", "postgresql_orders_table",
#             {"order_id": order_id}, {"found": False, "reason": "not_found"},
#         )
#         return {**state, "order_data": None}

#     if order.get("user_id") and order.get("user_id") != user_id:
#         log.warning(f"Order {order_id} does not belong to user {user_id}")
#         log_tool_span(
#             "fetch_order_data", "postgresql_orders_table",
#             {"order_id": order_id}, {"found": False, "reason": "unauthorized"},
#         )
#         return {**state, "order_data": None}

#     log.info(f"Order found and authorized: {order_id}")
#     log_tool_span(
#         "fetch_order_data", "postgresql_orders_table",
#         {"order_id": order_id}, {"found": True, "order": str(order)},
#         trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
#     )
#     return {**state, "order_data": order}


# # ─────────────────────────────────────────────
# # NODE 4 — error_response (UNCHANGED)
# # ─────────────────────────────────────────────

# def error_response(state: AgentState) -> AgentState:
#     log = get_log(state["request_id"], "order_agent", "error_response")
#     if state.get("response"):
#         return state
#     log.warning(f"Order not found: {state.get('order_id')}")
#     log_tool_span(
#         "error_response", "order_not_found",
#         {"order_id": state.get("order_id")},
#         {"message": "Order not found in database"},
#     )
#     return {
#         **state,
#         "response": f"Sorry, I could not find order #{state.get('order_id')}. Please check the order ID and try again.",
#     }


# # ─────────────────────────────────────────────
# # NODE 5 — generate_response (UNCHANGED)
# # ─────────────────────────────────────────────

# def generate_response(state: AgentState) -> AgentState:
#     log = get_log(state["request_id"], "order_agent", "generate_response")
#     log.info("LLM called")

#     prompt = f"""You are a helpful customer service assistant for an e-commerce platform.

# Order data: {str(state.get('order_data', {}))}
# Tracking info: {str(state.get('tracking_info', {}))}
# Customer asked: {state['current_input']}
# Conversation history: {str(state.get('messages', [])[-5:])}

# Analyze the order data and write a clear friendly response in 3-4 sentences.
# Always include customer name, current status, carrier name, tracking number and ETA.
# Sign off as: Customer Support Team"""

#     response      = llm.invoke(prompt)
#     usage         = response.usage_metadata
#     input_tokens  = usage.get("input_tokens",  0)
#     output_tokens = usage.get("output_tokens", 0)
#     cost          = log_llm_span(
#         span_name      = "generate_response",
#         prompt_text    = prompt,
#         response_text  = response.content,
#         input_tokens   = input_tokens,
#         output_tokens  = output_tokens,
#         model          = config.LLM_MODEL,
#         prompt_name    = "response_generation_prompt",
#         prompt_version = config.RESPONSE_GENERATION_PROMPT_VERSION,
#         trace_id       = state.get("mlflow_trace_id"),
#         parent_id      = state.get("mlflow_span_id"),
#     )

#     log.info("Response generated")
#     return {
#         **state,
#         "response":       response.content,
#         "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
#         "total_cost_usd": state["total_cost_usd"] + cost,
#     }


# # ─────────────────────────────────────────────
# # NODE 6 — save_to_db (UNCHANGED)
# # ─────────────────────────────────────────────

# def save_to_db(state: AgentState) -> AgentState:
#     log = get_log(state["request_id"], "order_agent", "save_to_db")
#     log.info("Saving response to DB")
#     save_message(
#         session_id    = state["session_id"],
#         role          = "assistant",
#         content       = state["response"],
#         agent_name    = "order_agent",
#         token_usage   = {
#             "total_tokens":   state["total_tokens"],
#             "total_cost_usd": state["total_cost_usd"],
#         },
#         mlflow_run_id = state.get("mlflow_run_id"),
#     )
#     log.info("Response saved")
#     return state


# # ─────────────────────────────────────────────
# # EDGES
# # ─────────────────────────────────────────────

# def validate_input_edge(state: AgentState) -> str:
#     if state.get("response"):
#         return "error_response"
#     if state.get("order_id"):
#         return "fetch_order_data"
#     return "fetch_order_listing"       # no order_id — go to listing tool


# def fetch_order_listing_edge(state: AgentState) -> str:
#     if state.get("order_id"):
#         return "fetch_order_data"       # arrival keyword matched single order
#     if state.get("response"):
#         return "save_to_db"             # listing response ready — save it
#     return "error_response"             # nothing found


# def order_found_edge(state: AgentState) -> str:
#     if state.get("order_data"):
#         return "shipment_tracking"
#     return "error_response"


# # ─────────────────────────────────────────────
# # BUILD ORDER AGENT GRAPH
# # ─────────────────────────────────────────────

# def build_order_agent():
#     graph = StateGraph(AgentState)

#     graph.add_node("validate_input",      validate_input)
#     graph.add_node("fetch_order_listing", fetch_order_listing)
#     graph.add_node("fetch_order_data",    fetch_order_data)
#     graph.add_node("shipment_tracking",   build_shipment_subgraph())
#     graph.add_node("generate_response",   generate_response)
#     graph.add_node("save_to_db",          save_to_db)
#     graph.add_node("error_response",      error_response)

#     graph.set_entry_point("validate_input")

#     graph.add_conditional_edges("validate_input", validate_input_edge, {
#         "fetch_order_data":    "fetch_order_data",
#         "fetch_order_listing": "fetch_order_listing",
#         "error_response":      "error_response",
#     })

#     graph.add_conditional_edges("fetch_order_listing", fetch_order_listing_edge, {
#         "fetch_order_data": "fetch_order_data",
#         "save_to_db":       "save_to_db",
#         "error_response":   "error_response",
#     })

#     graph.add_conditional_edges("fetch_order_data", order_found_edge, {
#         "shipment_tracking": "shipment_tracking",
#         "error_response":    "error_response",
#     })

#     graph.add_edge("shipment_tracking", "generate_response")
#     graph.add_edge("generate_response", "save_to_db")
#     graph.add_edge("save_to_db",        END)
#     graph.add_edge("error_response",    END)

#     return graph.compile()


# order_agent = build_order_agent()


# # ─────────────────────────────────────────────
# # TEST BLOCK
# # ─────────────────────────────────────────────
# if __name__ == "__main__":
#     from state import empty_state
#     from database import get_or_create_user, get_or_create_session

#     get_or_create_user("test-user")
#     session_id = get_or_create_session(None, "test-user")

#     state = empty_state(
#         session_id    = session_id,
#         user_id       = "test-user",
#         request_id    = "test-req-001",
#         messages      = [],
#         current_input = "where is my order #12345",
#     )

#     result = order_agent.invoke(state)
#     print(f"\n=== RESULT ===")
#     print(f"Order ID:  {result['order_id']}")
#     print(f"Response:  {result['response']}")
#     print(f"Tokens:    {result['total_tokens']}")
#     print(f"Cost:      ${result['total_cost_usd']}")
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
# HELPER
# ─────────────────────────────────────────────

def group_orders_by_status(orders: list) -> str:
    status_order = ["DELAYED", "PENDING", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "RETURNED"]
    emoji_map = {
        "DELAYED":          "🔴",
        "PENDING":          "🟡",
        "IN_TRANSIT":       "🚚",
        "OUT_FOR_DELIVERY": "📦",
        "DELIVERED":        "✅",
        "RETURNED":         "↩️",
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
# NODE 1 — validate_input (LLM ONLY)
# ─────────────────────────────────────────────

def validate_input(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "validate_input")
    log.info("Node entered")

    # ── Block guest users ─────────────────────────────────
    user_id = state.get("user_id", "")
    if user_id.endswith("@guest.com"):
        return {
            **state,
            "order_id": None,
            "response": "Guest users cannot access order information. Please sign up or log in to track your orders."
        }

    msg_lower = state["current_input"].lower()
    msg_upper = state["current_input"].upper()

    # ── Check explicit order ID first (no LLM needed) ────
    match = re.search(r'(ORD\d+)', msg_upper)
    if match:
        log.info(f"Explicit order ID found: {match.group(1)}")
        return {
            **state,
            "order_id":        match.group(1),
            "status_filter":   None,
            "product_keyword": None,
            "special_query":   None,
            "carrier_filter":  None,
            "shipping_mode":   None,
            "city_filter":     None,
            "min_price":       None,
            "max_price":       None,
            "query_limit":     10,
            "date_filter":     None,
            "month_filter":    None,
            "year_filter":     None,
        }

    # ── Check follow-up from history (no LLM needed) ─────
    followup_keywords = [
        "when will", "when does", "when it", "when was", "when did",
        "where is it", "will it arrive", "eta", "how long", "update",
        "delivery date", "tracking number", "current status",
        "what happened", "latest update", "track it", "has it", "did it",
        "what is the status", "what's the status", "status of",
        "tell me the status", "give me the status", "any update",
        "where is it now", "tell me more",
        "more details", "more info", "show details", "give me details",
        "is it delivered", "has it arrived",
        "what is the order", "order id", "order number",
        "give me the order", "what is the id", "tell me the order",
    ]
    is_followup = any(kw in msg_lower for kw in followup_keywords)

    msg_words     = [w for w in msg_lower.split() if len(w) > 3]
    stop_words    = {"what", "when", "where", "show", "list", "give", "tell", "find", "order", "orders", "will", "does", "have", "that", "this", "your", "mine"}
    content_words = [w for w in msg_words if w not in stop_words]
    has_product_mention = len(content_words) > 1 or (
    len(content_words) > 0 and not any(kw in msg_lower for kw in followup_keywords)
)

    if is_followup and not has_product_mention and state.get("messages"):
        for msg_item in reversed(state["messages"]):
            content = msg_item.get("content", "").upper()
            prev_match = re.search(r'(ORD\d+)', content)
            if prev_match:
                order_id = prev_match.group(1)
                log.info(f"Follow-up detected — reusing order_id={order_id}")
                return {
                    **state,
                    "order_id":        order_id,
                    "status_filter":   None,
                    "product_keyword": None,
                    "special_query":   None,
                    "carrier_filter":  None,
                    "shipping_mode":   None,
                    "city_filter":     None,
                    "min_price":       None,
                    "max_price":       None,
                    "query_limit":     10,
                    "date_filter":     None,
                    "month_filter":    None,
                    "year_filter":     None,
                }

    # ── Fetch product names for LLM context only ─────────
    import json as _json
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
                        product_names.add(item.lower())
            except:
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
- product_keyword: any product or item name the user mentions when asking about their orders (e.g. "SSD", "laptop", "keyboard", "webcam"). Extract it even if it does not appear in the ordered products list above — the user may be searching for it. NEVER set for shipping modes, carriers, or status words
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
- date_filter: if user mentions a specific date (e.g. "31-05-2026", "2026-05-31", "May 31 2026"), convert to YYYY-MM-DD format
- month_filter: if user mentions a month name or number without a specific day (e.g. "in May", "in May 2026", "month 5"), extract as 1-12 integer. Set null if date_filter is set
- year_filter: if user mentions a year (e.g. "in 2026", "placed in 2025"), extract as 4-digit integer
- If a specific date is given, set date_filter and leave month_filter/year_filter null

Return ONLY valid JSON. No explanation."""
    

    print(f"[DEBUG VALIDATE] Calling LLM for: {state['current_input']}")

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

        usage         = response.usage_metadata or {}
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost = log_llm_span(
            span_name     = "validate_input",
            prompt_text   = extraction_prompt,
            response_text = text,
            input_tokens  = input_tokens,
            output_tokens = output_tokens,
            model         = config.LLM_MODEL,
            prompt_name   = "validate_input",
            prompt_version= 1,
            trace_id      = state.get("mlflow_trace_id"),
            parent_id     = state.get("mlflow_span_id"),
        )

    except Exception as e:
        log.error(f"LLM extraction failed: {e}")
        extracted     = {
            "order_id": None, "status_filter": None, "product_keyword": None,
            "special_query": None, "carrier_filter": None, "shipping_mode": None,
            "city_filter": None, "min_price": None, "max_price": None, "limit": 10
        }
        input_tokens  = 0
        output_tokens = 0
        cost          = 0

    # ── Override limit when user explicitly says "all" ────
    if re.search(r'\ball\b', msg_lower) and re.search(r'\border', msg_lower):
        final_limit = 100
    else:
        final_limit = extracted.get("limit", 10)

    # ── Regex fallback for status_filter ─────────────────
    _STATUS_PATTERNS = [
        (r'\bpending\b',          "PENDING"),
        (r'\bdelayed\b',          "DELAYED"),
        (r'\bdelivered\b',        "DELIVERED"),
        (r'\breturned\b',         "RETURNED"),
        (r'\bin.transit\b',       "IN_TRANSIT"),
        (r'\bout.for.delivery\b', "OUT_FOR_DELIVERY"),
        (r'\bcancelled\b',        "CANCELLED"),
    ]
    if not extracted.get("status_filter"):
        for pattern, status in _STATUS_PATTERNS:
            if re.search(pattern, msg_lower):
                extracted["status_filter"] = status
                break

    # ── Date/month/year — regex-only, LLM values discarded ───────────
    # LLM is unreliable here: it guesses wrong years and defaults to the
    # 1st of the month when only a month name is mentioned. Pure regex is
    # more accurate and consistent.
    _MONTH_NAMES = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    extracted["date_filter"]  = None
    extracted["month_filter"] = None
    extracted["year_filter"]  = None

    # 1. Specific date patterns — set date_filter only
    m = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', msg_lower)
    if m:
        extracted["date_filter"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    else:
        m = re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', msg_lower)
        if m:
            extracted["date_filter"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            # "31 May 2026" or "May 31 2026" or "May 31, 2026"
            _mon_pat = '|'.join(_MONTH_NAMES)
            m = re.search(r'\b(\d{1,2})\s+(' + _mon_pat + r')\s+(\d{4})\b', msg_lower) or \
                re.search(r'\b(' + _mon_pat + r')\s+(\d{1,2})[,\s]+(\d{4})\b', msg_lower)
            if m:
                g = m.groups()
                if g[0].isdigit():
                    day, mon, yr = int(g[0]), _MONTH_NAMES[g[1]], int(g[2])
                else:
                    day, mon, yr = int(g[1]), _MONTH_NAMES[g[0]], int(g[2])
                extracted["date_filter"] = f"{yr}-{mon:02d}-{day:02d}"

    # 2. Month name (only if no specific date found)
    if not extracted["date_filter"]:
        for name, num in _MONTH_NAMES.items():
            if re.search(r'\b' + name + r'\b', msg_lower):
                extracted["month_filter"] = num
                break

    # 3. Year (only if no specific date found; present = filter to that year, absent = all years)
    if not extracted["date_filter"]:
        m = re.search(r'\b(20\d{2})\b', msg_lower)
        extracted["year_filter"] = int(m.group(1)) if m else None

    # ── Regex fallback for product_keyword ───────────────
    # Catches cases where LLM skips product_keyword because the item
    # isn't in the user's orders list (e.g. "how many SSD orders").
    if not extracted.get("product_keyword"):
        _IGNORE = {
            "my", "the", "all", "total", "of", "do", "i", "have",
            "how", "many", "any", "order", "orders", "there", "are",
            # status words — must never become product_keyword
            "pending", "delivered", "delayed", "returned",
            "transit", "in_transit", "out_for_delivery", "cancelled",
        }
        m = re.search(
            r'(?:how\s+many|count\s+of|number\s+of|any)\s+(\w+(?:[\s-]\w+)?)\s+order',
            msg_lower
        )
        if m:
            candidate = m.group(1).strip()
            if candidate not in _IGNORE:
                extracted["product_keyword"] = candidate

    # ── Always return all filters — NO DB QUERIES ─────────
    return {
        **state,
        "order_id":        extracted.get("order_id"),
        "status_filter":   extracted.get("status_filter"),
        "product_keyword": extracted.get("product_keyword"),
        "special_query":   extracted.get("special_query"),
        "carrier_filter":  extracted.get("carrier_filter"),
        "shipping_mode":   extracted.get("shipping_mode"),
        "city_filter":     extracted.get("city_filter"),
        "min_price":       extracted.get("min_price"),
        "max_price":       extracted.get("max_price"),
        "query_limit":     final_limit,
        "date_filter":     extracted.get("date_filter"),
        "month_filter":    extracted.get("month_filter"),
        "year_filter":     extracted.get("year_filter"),
        "total_tokens":    state.get("total_tokens", 0) + input_tokens + output_tokens,
        "total_cost_usd":  state.get("total_cost_usd", 0.0) + cost,
    }

    
# ─────────────────────────────────────────────
# NODE 2 — fetch_order_data (handles EVERYTHING)
# ─────────────────────────────────────────────

def fetch_order_data(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "fetch_order_data")
    log.info("Tool called: fetch_order_data")
    with mlflow.start_span(name="fetch_order_data", span_type="TOOL") as span:
        span.set_inputs({
            "order_id":      state.get("order_id"),
            "special_query": state.get("special_query"),
            "status_filter": state.get("status_filter"),
            "limit":         state.get("query_limit", 10),
        })
        result = _fetch_order_data_impl(state, log)
        span.set_outputs({
            "found":    bool(result.get("order_data") or result.get("response")),
            "has_data": bool(result.get("order_data")),
        })
    return result


def _fetch_order_data_impl(state: AgentState, log) -> AgentState:
    user_id         = state.get("user_id")
    order_id        = state.get("order_id")
    special_query   = state.get("special_query")
    status_filter   = state.get("status_filter")
    product_keyword = state.get("product_keyword")
    carrier_filter  = state.get("carrier_filter")
    shipping_mode   = state.get("shipping_mode")
    city_filter     = state.get("city_filter")
    min_price       = state.get("min_price")
    max_price       = state.get("max_price")
    limit           = state.get("query_limit", 10)
    date_filter     = state.get("date_filter")
    month_filter    = state.get("month_filter")
    year_filter     = state.get("year_filter")
    log.info(f"Query params — order_id={order_id} special={special_query} status={status_filter} product={product_keyword} carrier={carrier_filter} shipping={shipping_mode} limit={limit}")
    msg_lower       = state["current_input"].lower()
    
    

    # ── Single order fetch ────────────────────────────────
    if order_id:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM orders WHERE order_id = %s", [order_id])
                row   = cur.fetchone()
                order = dict(row) if row else None

        if not order:
            log.warning(f"Order not found: {order_id}")
            log_tool_span("fetch_order_data", "postgresql_orders_table",
                          {"order_id": order_id}, {"found": False, "reason": "not_found"})
            return {**state, "order_data": None,
                    "response": f"Sorry, I could not find order #{order_id}. Please check the order ID and try again."}

        if order.get("user_id") and order.get("user_id") != user_id:
            log.warning(f"Order {order_id} does not belong to user {user_id}")
            log_tool_span("fetch_order_data", "postgresql_orders_table",
                          {"order_id": order_id}, {"found": False, "reason": "unauthorized"})
            return {**state, "order_data": None,
                    "response": f"Sorry, order #{order_id} does not belong to your account."}

        log.info(f"Order found and authorized: {order_id}")
        log_tool_span("fetch_order_data", "postgresql_orders_table",
                      {"order_id": order_id}, {"found": True, "order": str(order)},
                      trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"))
        return {**state, "order_data": order}

    # ── Special queries ───────────────────────────────────
    if special_query == "count":
        count_conditions = ["user_id = %s"]
        count_params     = [user_id]
        if product_keyword:
            count_conditions.append("items::text ILIKE %s")
            count_params.append(f"%{product_keyword}%")
        if carrier_filter:
            count_conditions.append("carrier ILIKE %s")
            count_params.append(f"%{carrier_filter}%")
        if status_filter:
            count_conditions.append("status = %s")
            count_params.append(status_filter)
        if shipping_mode:
            count_conditions.append("shipping_mode ILIKE %s")
            count_params.append(f"%{shipping_mode}%")
        if city_filter:
            count_conditions.append("order_city ILIKE %s")
            count_params.append(f"%{city_filter}%")
        if min_price:
            count_conditions.append("sales_per_customer >= %s")
            count_params.append(float(min_price))
        if max_price:
            count_conditions.append("sales_per_customer <= %s")
            count_params.append(float(max_price))
        if date_filter:
            count_conditions.append("order_date::date = %s")
            count_params.append(date_filter)
        elif month_filter and year_filter:
            count_conditions.append("EXTRACT(MONTH FROM order_date::date) = %s AND EXTRACT(YEAR FROM order_date::date) = %s")
            count_params.extend([month_filter, year_filter])
        elif month_filter:
            count_conditions.append("EXTRACT(MONTH FROM order_date::date) = %s")
            count_params.append(month_filter)
        elif year_filter:
            count_conditions.append("EXTRACT(YEAR FROM order_date::date) = %s")
            count_params.append(year_filter)
        count_where = " AND ".join(count_conditions)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM orders WHERE {count_where}", count_params)
                total = cur.fetchone()[0]
                cur.execute(
                    f"SELECT status, COUNT(*) FROM orders WHERE {count_where} GROUP BY status ORDER BY COUNT(*) DESC",
                    count_params
                )
                breakdown = cur.fetchall()
        breakdown_lines = "\n".join([f"  • {s}: {c}" for s, c in breakdown])
        filter_parts = []
        if product_keyword:
            filter_parts.append(product_keyword)
        if carrier_filter:
            filter_parts.append(f"via {carrier_filter}")
        if status_filter:
            filter_parts.append(status_filter.lower().replace("_", " "))
        if shipping_mode:
            filter_parts.append(shipping_mode)
        filter_desc = " " + " ".join(filter_parts) if filter_parts else ""
        suffix = "in total" if not filter_parts else ""
        return {**state, "order_data": None,
                "response": f"You have {total}{filter_desc} orders{' ' + suffix if suffix else ''}.\n\nBreakdown:\n{breakdown_lines}"}

    elif special_query == "cheapest":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer ASC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your cheapest orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

    elif special_query == "most_expensive":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, items, sales_per_customer FROM orders WHERE user_id = %s ORDER BY sales_per_customer DESC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        lines = "\n".join([f"• {o['order_id']} — ₹{o['sales_per_customer']} — {o['items']} — {o['status']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your most expensive orders:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

    elif special_query == "last_week":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '7 days' ORDER BY order_date DESC LIMIT 10",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders from the last week."}
        lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your orders from the last week:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

    elif special_query == "last_month":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s AND order_date::date >= CURRENT_DATE - INTERVAL '30 days' ORDER BY order_date DESC LIMIT 10",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders from the last month."}
        lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your orders from the last month:\n\n{lines}\n\nReply with an Order ID to get full tracking details."}

    elif special_query == "late_risk":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
    "SELECT order_id, status, carrier, estimated_delivery, items, sales_per_customer FROM orders WHERE user_id = %s AND status NOT IN ('DELIVERED', 'RETURNED') ORDER BY order_date DESC LIMIT 10",
    [user_id]
)
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "None of your orders have a late delivery risk."}
        lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Delivery: {o['estimated_delivery']}) — Items: {o['items']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"These orders have a late delivery risk:\n\n{lines}\n\nReply with an Order ID for full details."}

    elif special_query == "upcoming":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
    "SELECT order_id, status, carrier, estimated_delivery, items, sales_per_customer FROM orders WHERE user_id = %s AND status NOT IN ('DELIVERED', 'RETURNED') ORDER BY order_date DESC LIMIT 10",
    [user_id]
)
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "All your orders have been delivered."}
        grouped = group_orders_by_status(orders)
        return {**state, "order_data": None,
                "response": f"Here are your upcoming orders:\n\n{grouped}\n\nReply with an Order ID for full details."}

    elif special_query == "recent":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s ORDER BY order_date DESC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders in our system yet."}
        lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your most recent orders:\n\n{lines}\n\nReply with an Order ID for full details."}

    elif special_query == "oldest":
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT order_id, status, carrier, estimated_delivery, items, order_date FROM orders WHERE user_id = %s ORDER BY order_date ASC LIMIT 5",
                    [user_id]
                )
                orders = [dict(r) for r in cur.fetchall()]
        if not orders:
            return {**state, "order_data": None, "response": "You have no orders in our system yet."}
        lines = "\n".join([f"• {o['order_id']} — {o['status']} via {o['carrier']} (Ordered: {o['order_date']}) — Items: {o['items']}" for o in orders])
        return {**state, "order_data": None,
                "response": f"Here are your oldest orders:\n\n{lines}\n\nReply with an Order ID for full details."}

    # ── Filter queries ────────────────────────────────────
    conditions = ["user_id = %s"]
    params     = [user_id]

    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)
    if product_keyword:
        conditions.append("items::text ILIKE %s")
        params.append(f"%{product_keyword}%")
    if carrier_filter:
        conditions.append("carrier ILIKE %s")
        params.append(f"%{carrier_filter}%")
    if shipping_mode:
        conditions.append("shipping_mode ILIKE %s")
        params.append(f"%{shipping_mode}%")
    if city_filter:
        conditions.append("order_city ILIKE %s")
        params.append(f"%{city_filter}%")
    if min_price:
        conditions.append("sales_per_customer >= %s")
        params.append(float(min_price))
    if max_price:
        conditions.append("sales_per_customer <= %s")
        params.append(float(max_price))
    if date_filter:
        conditions.append("order_date::date = %s")
        params.append(date_filter)
    elif month_filter and year_filter:
        conditions.append("EXTRACT(MONTH FROM order_date::date) = %s AND EXTRACT(YEAR FROM order_date::date) = %s")
        params.extend([month_filter, year_filter])
    elif month_filter:
        conditions.append("EXTRACT(MONTH FROM order_date::date) = %s")
        params.append(month_filter)
    elif year_filter:
        conditions.append("EXTRACT(YEAR FROM order_date::date) = %s")
        params.append(year_filter)

    where = " AND ".join(conditions)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
            f"""SELECT order_id, status, carrier, estimated_delivery, items, sales_per_customer, order_date
                FROM orders WHERE {where}
                ORDER BY order_date DESC LIMIT {limit}""",
            params
)
            orders = [dict(r) for r in cur.fetchall()]

    # Single match + arrival keyword → fetch full order directly
    arrival_keywords = ["when arrives", "when will", "when does", "when is", "arrives", "arrival"]
    if len(orders) == 1 and any(kw in msg_lower for kw in arrival_keywords):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM orders WHERE order_id = %s", [orders[0]["order_id"]])
                row = cur.fetchone()
                if row:
                    return {**state, "order_data": dict(row)}

    if not orders:
        if shipping_mode:
            return {**state, "order_data": None,
                    "response": f"I could not find any {shipping_mode} orders in your account."}
        elif product_keyword:
            return {**state, "order_data": None,
                    "response": f"I could not find any orders containing '{product_keyword}'. Would you like to see all your recent orders instead?"}
        elif carrier_filter:
            return {**state, "order_data": None,
                    "response": f"I could not find any orders shipped via '{carrier_filter}' in your account."}
        elif city_filter:
            return {**state, "order_data": None,
                    "response": f"I could not find any orders from '{city_filter}' in your account."}
        elif min_price or max_price:
            return {**state, "order_data": None,
                    "response": "I could not find any orders matching that price range."}
        elif date_filter:
            return {**state, "order_data": None,
                    "response": f"You have no orders placed on {date_filter}."}
        elif month_filter and year_filter:
            import calendar
            month_name = calendar.month_name[month_filter]
            return {**state, "order_data": None,
                    "response": f"You have no orders placed in {month_name} {year_filter}."}
        elif month_filter:
            import calendar
            month_name = calendar.month_name[month_filter]
            return {**state, "order_data": None,
                    "response": f"You have no orders placed in {month_name}."}
        elif year_filter:
            return {**state, "order_data": None,
                    "response": f"You have no orders placed in {year_filter}."}
        else:
            return {**state, "order_data": None,
                    "response": "You have no orders in our system yet."}

    grouped = group_orders_by_status(orders)
    return {
        **state,
        "order_data": None,
        "response": f"Here are your matching orders:\n\n{grouped}\n\nWhich order would you like to track? Reply with the Order ID (e.g. ORD2001)."
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
        "error_response", "order_not_found",
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
    recent  = str(state.get("messages", []))
    history_context = f"{summary}\nRecent: {recent}".strip()

    tracking = state.get("tracking_info") or {}
    raw_events = tracking.get("events") or []
    events_text = "\n".join(
        f"  • {str(e.get('time', ''))[:16].replace('T', ' ')} — {e.get('status', '')}"
        for e in raw_events
    ) if raw_events else "No events available."

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
# NODE 5 — save_to_db
# ─────────────────────────────────────────────

def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "order_agent", "save_to_db")
    log.info("Saving response to DB")
    with mlflow.start_span(name="save_to_db", span_type="TOOL") as span:
        span.set_inputs({"session_id": state["session_id"], "role": "assistant"})
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
        span.set_outputs({"status": "saved"})
    log.info("Response saved")
    return state


# ─────────────────────────────────────────────
# EDGES
# ─────────────────────────────────────────────

def validate_input_edge(state: AgentState) -> str:
    if state.get("response"):
        return "error_response"    # guest blocked
    return "fetch_order_data"      # always — handles everything


def order_found_edge(state: AgentState) -> str:
    if state.get("order_data"):
        return "shipment_tracking"  # single order — track it
    if state.get("response"):
        return "save_to_db"         # listing/special — save directly
    return "error_response"         # nothing found


# ─────────────────────────────────────────────
# BUILD ORDER AGENT GRAPH
# ─────────────────────────────────────────────

def build_order_agent():
    graph = StateGraph(AgentState)

    graph.add_node("validate_input",    validate_input)
    graph.add_node("fetch_order_data",  fetch_order_data)
    graph.add_node("shipment_tracking", build_shipment_subgraph())
    graph.add_node("generate_response", generate_response)
    graph.add_node("save_to_db",        save_to_db)
    graph.add_node("error_response",    error_response)

    graph.set_entry_point("validate_input")

    graph.add_conditional_edges("validate_input", validate_input_edge, {
        "fetch_order_data": "fetch_order_data",
        "error_response":   "error_response",
    })

    graph.add_conditional_edges("fetch_order_data", order_found_edge, {
        "shipment_tracking": "shipment_tracking",
        "save_to_db":        "save_to_db",
        "error_response":    "error_response",
    })

    graph.add_edge("shipment_tracking", "generate_response")
    graph.add_edge("generate_response", "save_to_db")
    graph.add_edge("save_to_db",        END)
    graph.add_edge("error_response",    END)

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
        session_id    = session_id,
        user_id       = "test-user",
        request_id    = "test-req-001",
        messages      = [],
        current_input = "where is my order ORD3005",
    )

    result = order_agent.invoke(state)
    print(f"\n=== RESULT ===")
    print(f"Order ID:  {result['order_id']}")
    print(f"Response:  {result['response']}")
    print(f"Tokens:    {result['total_tokens']}")
    print(f"Cost:      ${result['total_cost_usd']}")