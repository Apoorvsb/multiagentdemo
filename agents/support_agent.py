import re
import uuid
import json as _json
import mlflow
import psycopg2
import psycopg2.extras
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode

from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import calculate_cost, log_llm_span, log_tool_span
from database import get_conn, save_message


def _clean_response(text: str) -> str:
    text = re.sub(r"\[Your Name\]", "Customer Support Team", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Agent Name\]", "Customer Support Team", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Name\]", "Customer Support Team", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\[.*?(?:name|team|agent|rep|representative).*?\]", "Customer Support Team", text, flags=re.IGNORECASE
    )
    # Remove duplicate trailing signatures the LLM sometimes appends after [Your Name] substitution
    text = re.sub(r"\n+Customer Support (?:Agent|Representative|Team|Staff)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


llm = ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)

# session_id → {original_message, delivered_orders, issue_type}
_support_pending: dict = {}

_VALID_ISSUE_TYPES = {
    "damaged_goods",
    "missing_item",
    "wrong_item",
    "warranty_claim",
    "product_not_as_described",
    "account_issue",
    "refund_request",
    "payment_failed",
    "billing_inquiry",
    "delayed_delivery",
    "cancellation_request",
    "return_request",
    "technical_issue",
    "general_complaint",
    "show_tickets",
    "reopen_ticket",
}

# ── Sentiment triggers — escalate to P1 immediately ────────────────────────
_ANGRY_SIGNALS = [
    "unacceptable",
    "outrageous",
    "disgusting",
    "terrible",
    "worst",
    "horrible",
    "fraud",
    "cheated",
    "scam",
    "lied",
    "lawsuit",
    "consumer court",
    "legal action",
    "never again",
    "pathetic",
    "useless",
    "fed up",
    "furious",
    "appalling",
    "extremely disappointed",
    "very angry",
    "absolutely ridiculous",
]

# ── Ticket re-open triggers ─────────────────────────────────────────────────
_REOPEN_SIGNALS = [
    "still not resolved",
    "issue persists",
    "not fixed",
    "problem still exists",
    "still broken",
    "still wrong",
    "still not received",
    "not satisfied",
    "same problem again",
    "reopen",
    "re-open",
    "issue came back",
    "happening again",
]

_KEYWORD_OVERRIDES = {
    # ── Special: list tickets (short-circuits the whole support flow) ──
    "show_tickets": [
        "my tickets",
        "all tickets",
        "raised tickets",
        "show tickets",
        "list tickets",
        "ticket status",
        "my complaints",
        "all my tickets",
        "how all my",
        "how many tickets",
        "open tickets",
        "pending tickets",
        "tickets i have",
        "tickets i raised",
        "i have raised",
        "i raised",
        "show me the tickets",
        "view tickets",
        "view my tickets",
        "tickets raised",
        "have raised",
        "raised a ticket",
        "status of my ticket",
        "status of ticket",
        "check my ticket",
    ],
    # ── Re-open ────────────────────────────────────────────────────────
    "reopen_ticket": [
        "still not resolved",
        "issue persists",
        "not fixed",
        "problem still",
        "still broken",
        "still wrong",
        "still not received",
        "same problem again",
        "reopen",
        "re-open",
        "issue came back",
        "happening again",
        "not satisfied with resolution",
    ],
    # ── HIGH severity ─────────────────────────────────────────────────
    "damaged_goods": [
        "cracked screen",
        "arrived damaged",
        "broken",
        "cracked",
        "arrived with a crack",
        "damaged product",
        "damaged item",
        "want a replacement",
        "i want a replacement",
        "need a replacement",
        "want replacement",
    ],
    "wrong_item": [
        "wrong product",
        "wrong item",
        "received a wrong",
        "incorrect item",
        "incorrect product",
        "sent wrong",
    ],
    "missing_item": [
        "item missing",
        "missing from my package",
        "missing item",
        "item is missing",
        "not in the package",
        "not received",
        "did not receive",
        "never received",
        "order is missing",
        "my order is missing",
        "order missing",
        "package is missing",
        "package missing",
        "parcel missing",
        "parcel is missing",
        "shipment missing",
    ],
    "warranty_claim": [
        "warranty claim",
        "under warranty",
        "raise a warranty",
        "warranty issue",
        "claim warranty",
        "warranty period",
    ],
    "product_not_as_described": [
        "not working as described",
        "not as described",
        "product is not as",
        "not what was described",
        "different from description",
        "misleading description",
    ],
    "account_issue": [
        "account issue",
        "account problem",
        "login issue",
        "login problem",
        "cant login",
        "can't login",
        "account access",
        "account blocked",
        "account locked",
        "cannot access my account",
        "can't access my account",
    ],
    # ── MEDIUM severity ───────────────────────────────────────────────
    "refund_request": [
        "refund",
        "money back",
        "return money",
        "get my money",
        "want my money back",
        "i want a refund",
    ],
    "payment_failed": [
        "payment failed",
        "payment not processed",
        "deducted but",
        "amount deducted",
        "amount was deducted",
        "money deducted",
    ],
    "billing_inquiry": [
        "charged twice",
        "double charge",
        "wrong charge",
        "billing",
        "double charged",
        "duplicate charge",
    ],
    "delayed_delivery": [
        "delivery delayed",
        "not delivered yet",
        "late delivery",
        "order is delayed",
        "order delayed",
        "is delayed",
        "taking too long",
        "not arrived yet",
        "still not delivered",
    ],
    "cancellation_request": [
        "cancel my order",
        "cancel order",
        "want to cancel",
        "order cancellation",
        "cancel the order",
        "i want to cancel",
        "please cancel",
    ],
    "return_request": [
        "return my order",
        "want to return",
        "return request",
        "send it back",
        "return the",
        "i want to return",
        "return my product",
        "initiate return",
    ],
    # ── LOW severity ──────────────────────────────────────────────────
    "technical_issue": [
        "stopped working",
        "not working",
        "product stopped",
        "stopped after",
        "product is not working",
        "device not working",
        "product quality is poor",
        "quality is poor",
        "poor quality",
    ],
    "general_complaint": [
        "not happy with",
        "unhappy with",
        "packaging was bad",
        "bad packaging",
        "give feedback",
        "want to give feedback",
        "delivery experience",
        "poor service",
        "not satisfied",
        "disappointed",
        "bad experience",
    ],
}


def _fetch_delivered_orders(user_id: str) -> list:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT order_id, items, sales_per_customer, order_date, status
                       FROM orders
                       WHERE user_id = %s AND status = 'DELIVERED'
                       ORDER BY order_date DESC""",
                    [user_id],
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def _fetch_all_orders(user_id: str) -> list:
    """Fetch all orders (any status) — used for cancellation/return queries."""
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT order_id, items, sales_per_customer, order_date, status
                       FROM orders
                       WHERE user_id = %s
                       ORDER BY order_date DESC""",
                    [user_id],
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def _fetch_user_tickets(user_id: str) -> list:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT ticket_id, order_id, issue_type, priority, status, created_at, description
                       FROM tickets WHERE user_id = %s
                       ORDER BY created_at DESC""",
                    [user_id],
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def classify_issue(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "classify_issue")

    # ── Greetings / conversational messages ──────────────
    _msg = state["current_input"].lower().strip()

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
    if any(re.search(p, _msg) for p in _GOODBYE_PATTERNS):
        log.info("Goodbye detected")
        return {
            **state,
            "issue_type": "greeting",
            "response": "Goodbye! If you ever need support again, don't hesitate to reach out. Take care!",
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
    if any(re.search(p, _msg) for p in _THANKS_PATTERNS):
        log.info("Thanks detected")
        return {
            **state,
            "issue_type": "greeting",
            "response": "You're welcome! Is there anything else I can help you with?",
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
    if any(re.search(p, _msg) for p in _HOW_ARE_YOU_PATTERNS):
        log.info("How-are-you detected")
        return {
            **state,
            "issue_type": "greeting",
            "response": (
                "I'm doing well, thanks for asking! I'm here to help you with any support needs.\n\n"
                "- **Order issues** — tracking, delays, missing items\n"
                "- **Returns & refunds** — initiate or check status\n"
                "- **Damaged or wrong items** — raise a complaint\n"
                "- **Cancellations** — cancel an order\n\n"
                "What can I help you with today?"
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
        r"\bwho r you\b",
        r"\bhelp\b",
    ]
    if any(re.search(p, _msg) for p in _GREETING_PATTERNS):
        log.info("Greeting detected — returning intro response")
        return {
            **state,
            "issue_type": "greeting",
            "response": (
                "Hi! I'm your customer support assistant. I can help you with:\n\n"
                "- **Order issues** — tracking, delays, missing items\n"
                "- **Returns & refunds** — initiate or check status\n"
                "- **Damaged or wrong items** — raise a complaint\n"
                "- **Cancellations** — cancel an order\n"
                "- **Warranty & product issues** — get support\n\n"
                "Just tell me what's going on and I'll take care of it!"
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # ── Block guest users ─────────────────────────────────
    user_id = state.get("user_id", "")
    if user_id.endswith("@guest.com"):
        return {
            **state,
            "issue_type": "guest_blocked",
            "response": (
                "🚫 You don't have access to support features.\n\n"
                "Please **sign up** at /register with your email to raise complaints, "
                "request refunds, and track your support tickets."
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # Turn 2: user is responding with their order selection
    if state["session_id"] in _support_pending:
        user_input = state["current_input"].strip()
        delivered = _support_pending[state["session_id"]].get("delivered_orders", [])

        looks_like_selection = user_input.isdigit() or any(
            o["order_id"].upper() in user_input.upper() for o in delivered
        )

        if looks_like_selection:
            pending = _support_pending.pop(state["session_id"])
            order_id = None
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(delivered):
                    order_id = delivered[idx]["order_id"]
            else:
                for o in delivered:
                    if o["order_id"].upper() in user_input.upper():
                        order_id = o["order_id"]
                        break
            if not order_id and delivered:
                order_id = delivered[0]["order_id"]
            log.info(f"Order selected: {order_id}")
            return {
                **state,
                "current_input": pending["original_message"],
                "order_id": order_id,
                "issue_type": pending["issue_type"],
            }
        else:
            # New query — discard stale pending and reclassify
            _support_pending.pop(state["session_id"], None)
            log.info("Input is not an order selection — discarding pending, reclassifying")

    msg_lower = state["current_input"].lower()

    # ── Sentiment detection: angry/frustrated → force P1 escalation ──────────
    is_angry = any(sig in msg_lower for sig in _ANGRY_SIGNALS)
    if is_angry:
        log.info("Angry sentiment detected — will force PRIORITY_1 escalation")

    # ── Ticket re-open detection ──────────────────────────────────────────────
    if any(sig in msg_lower for sig in _REOPEN_SIGNALS):
        log.info("Ticket re-open request detected")
        # Find most recent resolved ticket for this user and re-open it
        try:
            with get_conn() as _conn:
                with _conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as _cur:
                    _cur.execute(
                        """SELECT ticket_id, issue_type, resolution FROM tickets
                           WHERE user_id=%s AND status='Resolved'
                           ORDER BY updated_at DESC LIMIT 1""",
                        [state.get("user_id", "")],
                    )
                    _resolved = _cur.fetchone()
                    if _resolved:
                        _cur.execute(
                            "UPDATE tickets SET status='Open', resolution=NULL, updated_at=NOW() WHERE ticket_id=%s",
                            [_resolved["ticket_id"]],
                        )
                        _conn.commit()
                        log.info(f"Re-opened ticket {_resolved['ticket_id']}")
                        return {
                            **state,
                            "issue_type": _resolved["issue_type"] or "general_complaint",
                            "response": (
                                f"I've re-opened your ticket **{_resolved['ticket_id']}** since the issue persists. "
                                "A support agent will review it with high priority and get back to you shortly. "
                                "We apologise for the inconvenience."
                            ),
                            "total_tokens": state.get("total_tokens", 0),
                            "total_cost_usd": state.get("total_cost_usd", 0.0),
                        }
        except Exception as _e:
            log.warning(f"Could not re-open ticket: {_e}")

    # ── Resolved ticket check: show resolution if user asks about it ──────────
    _RESOLUTION_CHECK = ["my ticket", "ticket status", "what happened", "resolved", "resolution", "ticket update"]
    if any(sig in msg_lower for sig in _RESOLUTION_CHECK):
        try:
            with get_conn() as _conn:
                with _conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as _cur:
                    _cur.execute(
                        """SELECT ticket_id, issue_type, resolution, updated_at FROM tickets
                           WHERE user_id=%s AND status='Resolved' AND resolution IS NOT NULL
                           ORDER BY updated_at DESC LIMIT 1""",
                        [state.get("user_id", "")],
                    )
                    _res = _cur.fetchone()
                    if _res:
                        _date = _res["updated_at"].strftime("%d %b %Y") if _res["updated_at"] else ""
                        log.info(f"Showing resolution for ticket {_res['ticket_id']}")
                        return {
                            **state,
                            "issue_type": "show_tickets",
                            "response": (
                                f"✅ Your ticket **{_res['ticket_id']}** was resolved on {_date}.\n\n"
                                f"**Resolution:** {_res['resolution']}\n\n"
                                "If the issue is still not resolved, type *'still not resolved'* and I'll re-open it."
                            ),
                            "total_tokens": state.get("total_tokens", 0),
                            "total_cost_usd": state.get("total_cost_usd", 0.0),
                        }
        except Exception as _e:
            log.warning(f"Could not fetch resolved ticket: {_e}")

    for _issue, _keywords in _KEYWORD_OVERRIDES.items():
        if any(kw in msg_lower for kw in _keywords):
            log.info(f"Keyword override — issue classified: {_issue}")
            state_update = {
                **state,
                "issue_type": _issue,
                "total_tokens": state.get("total_tokens", 0),
                "total_cost_usd": state.get("total_cost_usd", 0.0),
            }
            # Angry sentiment → inject into state so assign_priority can use it
            if is_angry:
                state_update["angry_sentiment"] = True
            return state_update

    log.info("LLM called")
    summary = state.get("conversation_summary") or ""
    recent = str(state.get("messages", []))
    history_context = f"{summary}\nRecent: {recent}".strip()

    prompt_template = mlflow.genai.load_prompt("prompts:/classify_issue_prompt/1")
    prompt = prompt_template.format(
        customer_message=state["current_input"],
        history=history_context,
    )

    try:
        response = llm.invoke(prompt)
        usage = response.usage_metadata
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        issue_type = response.content.strip().lower().replace(" ", "_")
        if issue_type not in _VALID_ISSUE_TYPES:
            log.warning(f"LLM returned unknown issue type '{issue_type}' — defaulting to general_complaint")
            issue_type = "general_complaint"
    except Exception as e:
        log.error(f"Classification failed: {e}")
        issue_type = "general_complaint"
        cost = 0.0
        input_tokens = 0
        output_tokens = 0
        response = type("R", (), {"content": issue_type})()

    log_llm_span(
        span_name="classify_issue",
        prompt_text=prompt,
        response_text=issue_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=config.LLM_MODEL,
        prompt_name="classify_issue_prompt",
        prompt_version=1,
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Issue classified: {issue_type}")
    return {
        **state,
        "issue_type": issue_type,
        "total_tokens": state["total_tokens"] + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def assess_severity(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "assess_severity")
    log.info("Node entered")

    issue_type = state.get("issue_type", "general_complaint")

    high_severity_issues = [
        "damaged_goods",
        "missing_item",
        "wrong_item",
        "warranty_claim",
        "account_issue",
        "product_not_as_described",
    ]
    medium_severity_issues = [
        "refund_request",
        "technical_issue",
        "billing_inquiry",
        "delayed_delivery",
        "payment_failed",
        "cancellation_request",
        "return_request",
    ]

    if issue_type in high_severity_issues:
        severity = "HIGH"
    elif issue_type in medium_severity_issues:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    log_tool_span(
        span_name="assess_severity",
        tool_name="severity_rules_engine",
        tool_input={"issue_type": issue_type},
        tool_output={"severity": severity},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Severity assessed: {severity}")
    return {**state, "severity": severity}


def severity_edge(state: AgentState) -> str:
    if state.get("severity") == "HIGH" or state.get("order_id") == "__PENDING__":
        return "escalation_handler"
    return "draft_resolution"


@tool
def get_support_policy(issue_type: str) -> str:
    """Fetch the support policy for a given issue type from the policies table.
    Falls back to general_complaint policy if no specific policy exists.
    Returns JSON with policy details or empty dict if not found.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM policies WHERE issue_type = %s", [issue_type])
                row = cur.fetchone()
                if not row:
                    cur.execute("SELECT * FROM policies WHERE issue_type = 'general_complaint'")
                    row = cur.fetchone()
        return _json.dumps(dict(row) if row else {}, default=str)
    except Exception:
        return _json.dumps({})


@tool
def get_ticket_history(user_id: str) -> str:
    """Fetch the last 5 support tickets for a user from the tickets table.
    Returns JSON list of tickets with ticket_id, issue_type, priority, status, created_at.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT ticket_id, issue_type, priority, status, created_at, description "
                    "FROM tickets WHERE user_id = %s ORDER BY created_at DESC LIMIT 5",
                    [user_id],
                )
                return _json.dumps([dict(r) for r in cur.fetchall()], default=str)
    except Exception:
        return _json.dumps([])


@tool
def create_support_ticket(
    ticket_id: str,
    user_id: str,
    session_id: str,
    issue_type: str,
    severity: str,
    priority: str,
    description: str,
    order_id: Optional[str] = None,
) -> str:
    """Insert a new support ticket — checks for duplicate open ticket first.
    Returns JSON with ticket_id on success or error message on failure.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Duplicate detection: check for open ticket on same order+issue_type
                if order_id:
                    cur.execute(
                        """SELECT ticket_id, created_at FROM tickets
                           WHERE user_id=%s AND order_id=%s AND issue_type=%s AND status='Open'
                           ORDER BY created_at DESC LIMIT 1""",
                        [user_id, order_id, issue_type],
                    )
                    existing = cur.fetchone()
                    if existing:
                        return _json.dumps(
                            {
                                "ticket_id": existing["ticket_id"],
                                "status": "already_open",
                                "message": f"An open ticket {existing['ticket_id']} already exists for this order and issue.",
                            }
                        )

                cur.execute(
                    """INSERT INTO tickets
                       (ticket_id, user_id, session_id, order_id, issue_type,
                        severity, priority, status, description)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [ticket_id, user_id, session_id, order_id, issue_type, severity, priority, "Open", description],
                )
        return _json.dumps({"ticket_id": ticket_id, "status": "created"})
    except Exception as e:
        return _json.dumps({"ticket_id": "TKT_ERROR", "error": str(e)})


# ToolNode for support tools
support_tool_node = ToolNode([get_support_policy, get_ticket_history, create_support_ticket])


def lookup_policy(state: AgentState) -> AgentState:
    """Fetches support policy via ToolNode (get_support_policy)."""
    log = get_log(state["request_id"], "support_agent", "lookup_policy")
    log.info("Tool called: lookup_policy via ToolNode")

    issue_type = state.get("issue_type", "general_complaint")
    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_support_policy", "args": {"issue_type": issue_type}, "id": call_id, "type": "tool_call"}
        ],
    )
    result = support_tool_node.invoke({"messages": [ai_msg]})
    policy = _json.loads(result["messages"][-1].content) or None

    log_tool_span(
        span_name="lookup_policy",
        tool_name="postgresql_policies_table",
        tool_input={"issue_type": issue_type},
        tool_output={"found": bool(policy), "policy": str(policy)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    # HIGH severity issues need the user to pick their delivered order
    _HIGH_ORDER_ISSUES = {
        "damaged_goods",
        "missing_item",
        "wrong_item",
        "warranty_claim",
        "product_not_as_described",
    }
    # MEDIUM severity issues also need order context (refund/return/cancel)
    _MEDIUM_ORDER_ISSUES = {
        "refund_request",
        "return_request",
        "cancellation_request",
    }

    issue_type = state.get("issue_type", "general_complaint")

    if not state.get("order_id"):
        if state.get("severity") == "HIGH" and issue_type in _HIGH_ORDER_ISSUES:
            orders = _fetch_delivered_orders(state["user_id"])
        elif issue_type in _MEDIUM_ORDER_ISSUES:
            # cancellation needs all orders (including pending/in-transit)
            orders = _fetch_all_orders(state["user_id"])
        else:
            orders = []

        if orders:
            _support_pending[state["session_id"]] = {
                "original_message": state["current_input"],
                "delivered_orders": orders,
                "issue_type": issue_type,
            }
            log.info("Awaiting order selection from user")
            return {**state, "policy": policy, "order_id": "__PENDING__"}

    log.info(f"Policy found: {bool(policy)}")
    return {**state, "policy": policy}


# ── Escalation subgraph nodes ─────────────────────────────


def check_history(state: AgentState) -> AgentState:
    """Fetches ticket history via ToolNode (get_ticket_history)."""
    log = get_log(state["request_id"], "support_agent", "check_history")

    if state.get("order_id") == "__PENDING__":
        return state

    log.info("Checking complaint history via ToolNode")
    user_id = state.get("user_id")

    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_ticket_history", "args": {"user_id": user_id}, "id": call_id, "type": "tool_call"}],
    )
    result = support_tool_node.invoke({"messages": [ai_msg]})
    previous_tickets = _json.loads(result["messages"][-1].content)
    ticket_count = len(previous_tickets)

    log_tool_span(
        span_name="check_history",
        tool_name="postgresql_tickets_table",
        tool_input={"user_id": user_id},
        tool_output={"ticket_count": ticket_count},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    # Check if an open ticket already exists for this specific order
    order_id = state.get("order_id")
    existing_ticket = None
    if order_id:
        for t in previous_tickets:
            if order_id in (t.get("description") or "") and t.get("status") not in ("Closed", "Resolved"):
                existing_ticket = t
                break

    log.info(f"Found {ticket_count} previous tickets")
    return {
        **state,
        "previous_tickets": previous_tickets,
        "ticket_count": ticket_count,
        "ticket_id": existing_ticket["ticket_id"] if existing_ticket else None,
    }


def assign_priority(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "assign_priority")

    if state.get("order_id") == "__PENDING__" or state.get("ticket_id"):
        return state

    ticket_count = state.get("ticket_count", 0)
    severity = state.get("severity", "LOW")

    # Angry/frustrated customer → always PRIORITY_1
    if state.get("angry_sentiment"):
        log.info("Angry sentiment flag set — assigning PRIORITY_1")
        priority = "PRIORITY_1"
    elif severity == "HIGH" and ticket_count >= 2:
        priority = "PRIORITY_1"
    elif severity == "HIGH":
        priority = "PRIORITY_2"
    elif severity == "MEDIUM" and ticket_count >= 2:
        priority = "PRIORITY_2"
    elif severity == "MEDIUM":
        priority = "PRIORITY_3"
    else:
        priority = "PRIORITY_4"

    log_tool_span(
        span_name="assign_priority",
        tool_name="priority_rules_engine",
        tool_input={"severity": severity, "ticket_count": ticket_count},
        tool_output={"priority": priority},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Priority assigned: {priority}")
    return {**state, "priority": priority}


def create_ticket(state: AgentState) -> AgentState:
    """Creates a support ticket via ToolNode (create_support_ticket)."""
    log = get_log(state["request_id"], "support_agent", "create_ticket")

    if state.get("order_id") == "__PENDING__" or state.get("ticket_id"):
        return state

    log.info("Tool called: create_ticket via ToolNode")
    ticket_id = f"TKT{str(uuid.uuid4())[:8].upper()}"
    order_ref = f"[Order: {state.get('order_id')}] " if state.get("order_id") else ""
    description = (order_ref + state["current_input"])[:500]
    order_id = state.get("order_id") if state.get("order_id") != "__PENDING__" else None

    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "create_support_ticket",
                "args": {
                    "ticket_id": ticket_id,
                    "user_id": state.get("user_id"),
                    "session_id": state.get("session_id"),
                    "issue_type": state.get("issue_type"),
                    "severity": state.get("severity"),
                    "priority": state.get("priority"),
                    "description": description,
                    "order_id": order_id,
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )
    result = support_tool_node.invoke({"messages": [ai_msg]})
    data = _json.loads(result["messages"][-1].content)
    ticket_id = data.get("ticket_id", "TKT_ERROR")
    log.info(f"Ticket created: {ticket_id}")

    log_tool_span(
        span_name="create_ticket",
        tool_name="postgresql_tickets_table",
        tool_input={"issue_type": state.get("issue_type"), "priority": state.get("priority")},
        tool_output={"ticket_id": ticket_id},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    return {**state, "ticket_id": ticket_id}


def build_escalation_subgraph():
    sub = StateGraph(AgentState)
    sub.add_node("check_history", check_history)
    sub.add_node("assign_priority", assign_priority)
    sub.add_node("create_ticket", create_ticket)
    sub.set_entry_point("check_history")
    sub.add_edge("check_history", "assign_priority")
    sub.add_edge("assign_priority", "create_ticket")
    sub.add_edge("create_ticket", END)
    return sub.compile()


def draft_resolution(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "draft_resolution")
    log.info("LLM called")

    # ── Cancellation policy check ─────────────────────────────────────────────
    # Block cancellation if the order is already in transit or out for delivery.
    if state.get("issue_type") == "cancellation_request":
        order_id = state.get("order_id")
        if order_id and order_id != "__PENDING__":
            try:
                from database import get_conn
                import psycopg2.extras

                with get_conn() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT status FROM orders WHERE order_id = %s", [order_id])
                        row = cur.fetchone()
                        if row:
                            status = row["status"].upper()
                            if status in ("IN_TRANSIT", "OUT_FOR_DELIVERY"):
                                log.info(f"Cancellation blocked — order {order_id} is {status}")
                                return {
                                    **state,
                                    "response": (
                                        f"I'm sorry, but **{order_id}** cannot be cancelled at this stage — "
                                        f"it is currently **{status.replace('_', ' ').title()}** and is already on its way to you.\n\n"
                                        "Once you receive the item, you can:\n"
                                        "- **Return it** — raise a return request within the return window\n"
                                        "- **Refuse delivery** — ask the delivery agent to return it\n\n"
                                        "Would you like help with anything else?"
                                    ),
                                }
                            elif status == "DELIVERED":
                                log.info(f"Cancellation blocked — order {order_id} already DELIVERED")
                                return {
                                    **state,
                                    "response": (
                                        f"**{order_id}** has already been **Delivered** and cannot be cancelled. "
                                        "If you'd like to return it, I can raise a return request for you. Would you like to proceed?"
                                    ),
                                }
            except Exception as e:
                log.warning(f"Could not check order status for cancellation: {e}")

    policy = state.get("policy", {})
    ticket_id = state.get("ticket_id")
    prompt_template = mlflow.genai.load_prompt("prompts:/draft_resolution_prompt/1")
    from datetime import datetime

    prompt = prompt_template.format(
        customer_message=state["current_input"],
        issue_type=state.get("issue_type", ""),
        severity=state.get("severity", "LOW"),
        policy_text=policy.get("policy_text", "") if policy else "",
        ticket_id=str(ticket_id or "N/A"),
        current_date=datetime.now().strftime("%B %d, %Y"),
    )

    try:
        response = llm.invoke(prompt)
        usage = response.usage_metadata
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        resolution = _clean_response(response.content)
    except Exception as e:
        log.error(f"Draft resolution failed: {e}")
        resolution = f"We have received your complaint and will resolve it within 24 hours.{f' Ticket: {ticket_id}.' if ticket_id else ''}"
        cost = 0.0
        input_tokens = 0
        output_tokens = 0

    log_llm_span(
        span_name="draft_resolution",
        prompt_text=prompt,
        response_text=resolution,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=config.LLM_MODEL,
        prompt_name="draft_resolution_prompt",
        prompt_version=1,
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info("Resolution drafted")
    return {
        **state,
        "response": resolution,
        "total_tokens": state["total_tokens"] + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def generate_escalation_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "generate_escalation_response")

    # Awaiting order selection — show the user their delivered orders
    if state.get("order_id") == "__PENDING__":
        pending = _support_pending.get(state["session_id"], {})
        delivered = pending.get("delivered_orders", [])
        import json as _j

        # Extract product keyword from original message and filter orders
        original_msg = pending.get("original_message", "").lower()
        _STOP = {
            "my",
            "the",
            "a",
            "an",
            "of",
            "for",
            "i",
            "want",
            "need",
            "refund",
            "return",
            "cancel",
            "complaint",
            "issue",
            "order",
            "orders",
            "about",
            "with",
            "this",
            "that",
            "damaged",
            "wrong",
            "broken",
            "cracked",
            "defective",
            "faulty",
            "missing",
            "came",
            "come",
            "arrived",
            "arrive",
            "delivered",
            "delivery",
            "not",
            "haven",
            "havent",
            "received",
            "receive",
            "recent",
            "latest",
            "all",
            "show",
            "track",
            "status",
            "product",
            "item",
            "please",
            "help",
            "got",
        }
        words = [w for w in re.findall(r"\b\w+\b", original_msg) if w not in _STOP and len(w) > 2]
        keyword = " ".join(words[:2]) if words else ""

        if keyword:
            filtered = [o for o in delivered if keyword.lower() in str(o.get("items", "")).lower()]
        else:
            filtered = []

        if filtered:
            display_orders = filtered
            header = f"I found {len(filtered)} order(s) matching **{keyword}**. Which one is this about?\n"
        else:
            display_orders = delivered[:10]
            header = (
                (
                    f"I couldn't find an order for **{keyword}** in your history. "
                    f"Please select from your recent orders:\n"
                )
                if keyword
                else "I'd like to help with your issue. Which order is this about?\n"
            )

        lines = [header]
        for i, o in enumerate(display_orders, 1):
            raw = o.get("items", [])
            if isinstance(raw, str):
                try:
                    raw = _j.loads(raw)
                except Exception:
                    pass
            items_str = ", ".join(raw) if isinstance(raw, list) else str(raw)
            lines.append(f"{i}. **{o['order_id']}** — {items_str} (₹{o.get('sales_per_customer', '')})")
        lines.append("\nType the number or Order ID:")
        return {**state, "response": "\n".join(lines)}

    ticket_id = state.get("ticket_id", "N/A")
    previous_tickets = state.get("previous_tickets") or []
    priority = state.get("priority", "PRIORITY_3")
    policy = state.get("policy", {})
    priority_sla = {
        "PRIORITY_1": "2 hours",
        "PRIORITY_2": "4 hours",
        "PRIORITY_3": "24 hours",
        "PRIORITY_4": "48 hours",
    }
    sla = priority_sla.get(priority, "24 hours")

    # Existing open ticket for this order — no need to create a new one
    is_existing = any(t.get("ticket_id") == ticket_id for t in previous_tickets)
    if is_existing:
        order_id = state.get("order_id", "")
        issue_label = (state.get("issue_type") or "issue").replace("_", " ")
        return {
            **state,
            "response": (
                f"I found an existing open ticket **{ticket_id}** already raised for your "
                f"**{issue_label}** on order **{order_id}**. "
                f"Our support team is already working on it and will get back to you within {sla}. "
                f"No new ticket has been created."
            ),
        }

    prompt_template = mlflow.genai.load_prompt("prompts:/escalation_response_prompt/1")
    prompt = prompt_template.format(
        customer_message=state["current_input"],
        issue_type=state.get("issue_type", ""),
        priority=priority,
        ticket_id=str(ticket_id),
        sla=sla,
        policy_text=policy.get("policy_text", "") if policy else "",
    )

    try:
        response = llm.invoke(prompt)
        usage = response.usage_metadata
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        resolution = _clean_response(response.content)
    except Exception as e:
        log.error(f"Escalation response failed: {e}")
        resolution = (
            f"Your complaint has been escalated with ticket ID {ticket_id}. Our team will contact you within {sla}."
        )
        cost = 0.0
        input_tokens = 0
        output_tokens = 0

    log_llm_span(
        span_name="generate_escalation_response",
        prompt_text=prompt,
        response_text=resolution,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=config.LLM_MODEL,
        prompt_name="escalation_response_prompt",
        prompt_version=1,
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info("Escalation response generated")
    return {
        **state,
        "response": resolution,
        "total_tokens": state["total_tokens"] + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def list_tickets_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "list_tickets_response")
    log.info("Fetching all tickets for user")

    tickets = _fetch_user_tickets(state["user_id"])

    if not tickets:
        response = "You haven't raised any support tickets yet."
    else:
        lines = [f"Here are all your raised tickets ({len(tickets)} total):\n"]
        for i, t in enumerate(tickets, 1):
            created = t.get("created_at")
            date_str = created.strftime("%b %d, %Y") if created else "N/A"
            issue = (t.get("issue_type") or "general").replace("_", " ").title()
            status = t.get("status", "N/A")
            priority = t.get("priority", "N/A")
            tid = t.get("ticket_id", "N/A")
            order_id = t.get("order_id") or "N/A"
            lines.append(f"{i}. **{tid}** | Order: {order_id} | {issue} | Status: {status} | {priority} | {date_str}")
        response = "\n".join(lines)

    log_tool_span(
        span_name="list_tickets_response",
        tool_name="postgresql_tickets_table",
        tool_input={"user_id": state["user_id"]},
        tool_output={"ticket_count": len(tickets)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Listed {len(tickets)} tickets")
    return {**state, "response": response}


def classify_issue_edge(state: AgentState) -> str:
    if state.get("response"):
        # greeting, guest_blocked, or any pre-filled response — skip the full support flow
        return "save_to_db"
    if state.get("issue_type") == "show_tickets":
        return "list_tickets_response"
    return "assess_severity"


def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "save_to_db")
    log.info("Saving response to DB")
    with mlflow.start_span(name="save_to_db", span_type="TOOL") as span:
        span.set_inputs({"session_id": state["session_id"], "role": "assistant"})
        save_message(
            session_id=state["session_id"],
            role="assistant",
            content=state["response"],
            agent_name="support_agent",
            token_usage={
                "total_tokens": state["total_tokens"],
                "total_cost_usd": state["total_cost_usd"],
            },
            mlflow_run_id=state.get("mlflow_run_id"),
        )
        span.set_outputs({"status": "saved"})
    log.info("Response saved")
    return state


def build_support_agent():
    graph = StateGraph(AgentState)

    graph.add_node("classify_issue", classify_issue)
    graph.add_node("assess_severity", assess_severity)
    graph.add_node("lookup_policy", lookup_policy)  # calls support_tool_node internally
    graph.add_node("support_tools", support_tool_node)  # ToolNode — policy, history, ticket
    graph.add_node("escalation_handler", build_escalation_subgraph())
    graph.add_node("draft_resolution", draft_resolution)
    graph.add_node("generate_escalation_response", generate_escalation_response)
    graph.add_node("list_tickets_response", list_tickets_response)
    graph.add_node("save_to_db", save_to_db)

    graph.set_entry_point("classify_issue")
    graph.add_conditional_edges(
        "classify_issue",
        classify_issue_edge,
        {
            "save_to_db": "save_to_db",
            "list_tickets_response": "list_tickets_response",
            "assess_severity": "assess_severity",
        },
    )
    graph.add_edge("list_tickets_response", "save_to_db")
    graph.add_edge("assess_severity", "lookup_policy")

    graph.add_conditional_edges(
        "lookup_policy",
        severity_edge,
        {
            "escalation_handler": "escalation_handler",
            "draft_resolution": "draft_resolution",
        },
    )

    graph.add_edge("escalation_handler", "generate_escalation_response")
    graph.add_edge("generate_escalation_response", "save_to_db")
    graph.add_edge("draft_resolution", "save_to_db")
    graph.add_edge("save_to_db", END)

    return graph.compile()


support_agent = build_support_agent()


if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    test_cases = [
        "my laptop arrived with a cracked screen",
        "I want to cancel my order",
        "I was charged twice for the same order",
    ]

    for msg in test_cases:
        print(f"\n--- Testing: '{msg}' ---")
        state = empty_state(
            session_id=session_id,
            user_id="test-user",
            request_id="test-req-003",
            messages=[],
            current_input=msg,
        )
        result = support_agent.invoke(state)
        print(f"Issue:    {result.get('issue_type')}")
        print(f"Severity: {result.get('severity')}")
        print(f"Ticket:   {result.get('ticket_id')}")
        print(f"Response: {result['response'][:100]}...")
