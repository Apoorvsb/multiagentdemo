import re
import mlflow  # noqa: F401
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
from agents.order_agent import order_agent
from agents.product_agent import product_agent
from agents.support_agent import support_agent, _support_pending

setup_mlflow()

llm = ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)


# ═══════════════════════════════════════════════════════
# INTENT ROUTER
# ═══════════════════════════════════════════════════════


class IntentOutput(BaseModel):
    intent: Literal["order_query", "product_query", "support_query", "out_of_scope"]


def intent_router(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "router", "intent_router")
    log.info("Node entered")

    _msg_lower = state["current_input"].lower().strip()

    # ── Fast-path for conversational messages (greetings, farewells, thanks) ──
    # Route to product_agent which handles all of these gracefully.
    # Checked first so "bye" never falls to out_of_scope.
    _CONVERSATIONAL_FASTPATH = [
        r"^(?:bye|goodbye|good\s*bye|see\s+you|see\s+ya|cya|ttyl|take\s+care|good\s+night|adios|cheers)[\s!.]*$",
        r"^(?:hi+|hello+|hey+|hiya|howdy|greetings|good\s+(?:morning|afternoon|evening))"
        r"(?:\s+(?:there|friend|everyone|all|sir|ma'?am))?[\s!.]*$",
        r"^(?:thanks?|thank\s+you|thank\s+u|thx|ty|appreciate)[\s!.]*$",
        r"^how\s+(?:are\s+you|r\s+u|is\s+it\s+going)",
        r"^(?:who|what)\s+are\s+you\b",
        r"^what\s+can\s+you\s+do\b",
    ]
    if any(re.search(p, _msg_lower) for p in _CONVERSATIONAL_FASTPATH):
        log.info("Conversational fast-path matched — routing to product_agent")
        _support_pending.pop(state["session_id"], None)
        return {**state, "intent": "product_query"}

    # ── Support fast-path: unambiguous complaint/issue phrases → support_agent ──
    _SUPPORT_FASTPATH = re.compile(
        r"\b(?:"
        r"(?:my\s+)?order\s+is\s+(?:missing|damaged|broken|wrong|lost)|"
        r"haven(?:'t|t)\s+received|not\s+received\s+(?:my\s+)?order|"
        r"my\s+(?:package|parcel|item)\s+is\s+(?:missing|lost|not\s+arrived)|"
        r"order\s+came\s+(?:broken|damaged|wrong)|"
        r"received\s+(?:wrong|damaged|broken)|"
        r"arrived\s+(?:damaged|broken|wrong|defective)|"
        r"\w+\s+arrived\s+(?:damaged|broken|wrong|defective)|"
        r"warranty\s+claim|raise\s+a\s+warranty|warranty\s+issue|"
        r"my\s+order\s+(?:hasn(?:'t|t)\s+arrived|is\s+missing|never\s+arrived)|"
        r"(?:i\s+(?:want|need|would\s+like)\s+(?:a\s+)?|give\s+me\s+(?:a\s+)?|initiate\s+(?:a\s+)?)"
        r"(?:refund|return|replacement|cancellation)|"
        r"(?:want\s+to\s+|need\s+to\s+)?(?:cancel|return)\s+(?:my\s+)?order|"
        r"tickets?|raised?\s+(?:a\s+)?ticket"
        r")\b"
    )
    if _SUPPORT_FASTPATH.search(_msg_lower):
        log.info("Support fast-path matched — routing to support_agent")
        return {**state, "intent": "support_query"}

    # ── Regex fast-path for unambiguous product queries ───────────────────────
    # Checked BEFORE the _support_pending lock so a clear shopping intent always
    # escapes a stuck support session (e.g. user asked support, then says "show me laptops").
    # Pre-check: if message clearly talks about the user's own orders, skip fast-path entirely
    _ORDER_INTENT = re.compile(
        r"\b(?:my\s+(?:order|orders|recent\s+orders|all\s+orders)|"
        r"all\s+(?:my\s+)?(?:recent\s+)?orders?|"
        r"show\s+(?:all\s+)?(?:my\s+)?(?:recent\s+)?orders?|"
        r"recent\s+orders?|tickets?)\b"
    )
    _PRODUCT_FASTPATH = [
        r"\bbest\s+\w",  # "best headphones", "best laptop under 50k"
        r"\bshow\s+best\b",  # "show best headphones"
        r"\bshow\s+me\b(?!\s+(?:my\s+)?(?:ticket|refund|order|complaint))",
        r"\bshow\s+(?!(?:my\s+)?(?:ticket|refund|complaint))\w",
        r"\bfind\s+(?:me\s+)?(a\s+)?(?:good|best|cheap|top|nice|affordable|something)\b",
        r"\bi\s+(?:need|want|am\s+looking\s+for)\s+(?:a\s+|some\s+)?"
        r"(?!(?:refund|return|replacement|cancellation|cancel|warranty|raise|complaint|ticket))\w",
        r"\blooking\s+for\s+(?:a\s+|some\s+)?\w",
        r"\bsomething\s+(?:good|nice|cheap|affordable|best|top|for)\b",
        r"\brecommend\b",  # "recommend a good TV"
        r"\bcompare\b",  # "compare Sony vs Bose"
        r"\btop[\s-]rated\b",  # "top rated phones"
        r"\bunder\s+(?:rs\.?|₹)?\d+",  # "headphones under 5000"
        r"\bcheapest\b",  # "cheapest earbuds"
        r"\bshow\s+(?:me\s+)?(?:all\s+)?\w+\s+products?\b",  # "show HP products"
        r"\bshow\s+(?:me\s+)?(?:all\s+)?\w+\s+"
        r"(?:laptops?|phones?|tvs?|headphones?|earbuds?|speakers?|keyboards?|mice|mouse|monitors?|tablets?|cameras?)\b",
        r"\bwhat\s+brands?\b",  # "what brands do you have"
        r"\bwhat\s+(?:products?|do\s+you\s+(?:have|sell))\b",
        r"^only\s+\w",  # "only hawkins", "only samsung"
        r"^just\s+\w",  # "just boAt", "just hp"
        r"^\w+\s+only$",  # "samsung only", "hp only"
        r"\babove\s+\d",  # "above 4 stars", "above 1000"
        r"\bbelow\s+\d",  # "below 2000"
        r"\bbetween\s+\d",  # "between 500 and 2000"
        r"\d+\s*(?:star|rating)s?\s+(?:and\s+)?(?:above|below|over)",  # "4 stars and above"
        r"(?:highest|most)\s+(?:discount|rated|reviewed)",  # sort refinements
        r"^(?:cheapest|budget|premium|latest|newest|highest[\s-]rated|top[\s-]rated)$",
    ]
    if not _ORDER_INTENT.search(_msg_lower) and any(re.search(p, _msg_lower) for p in _PRODUCT_FASTPATH):
        log.info("Product fast-path matched — skipping LLM router")
        # Also clear any stuck support-pending state so the user can freely browse
        _support_pending.pop(state["session_id"], None)
        return {**state, "intent": "product_query"}

    # ── Support pending lock (only for messages that didn't match product fast-path) ──
    if state["session_id"] in _support_pending:
        log.info("Session awaiting support order selection — routing to support_agent")
        return {**state, "intent": "support_query"}

    prompt = f"""You are an intent classifier for an e-commerce assistant
that handles orders, products, and customer support.

Classify the user message into exactly one of these four intents:

**order_query** — user is asking about THEIR OWN orders, deliveries, shipments, or purchase history.
Examples:
- "where is my order", "track my package", "when will it arrive"
- "show my orders", "my order is delayed", "did my phone arrive"
- "orders in june 2026", "my sunglasses order", "orders above 500"
- "status of my order ORD123", "show delivered orders", "show pending orders"

**product_query** — user wants to find, browse, compare, or get recommendations for products to buy.
Examples:
- "show me laptops under 50000", "best earphones under 2000"
- "recommend a good pressure cooker", "compare Sony vs Bose headphones"
- "show boAt earphones", "find me a gaming mouse", "top rated phones"
- "show best headphones", "best tv", "find good speakers", "show philips products"
- "show me headphones", "find me earbuds", "good laptops under 60000"
- "find me kettle", "find me fans", "find me microwaves", "find me a laptop"
- "get me earbuds", "get me a phone", "looking for headphones"

**support_query** — user has a problem, complaint, issue, or needs help. Includes:
- Greetings and introductions: "hi", "hello", "who are you", "what can you do"
- Delivery issues: "not received", "shows delivered but not arrived", "marked as delivered but missing",
  "my order is missing", "order is missing", "my package is missing", "haven't received my order",
  "my order hasn't arrived", "parcel not received", "item not delivered"
- Product issues: "damaged", "wrong item", "missing from package", "not working", "cracked",
  "my order came broken", "received wrong product", "item is defective"
- Refunds & payments: "refund", "payment failed", "charged twice", "wrong charge"
- Returns & cancellations: "cancel my order", "cancel order", "want to cancel",
  "want to return", "send it back", "return my order"
- Warranty: "warranty claim", "stopped working", "product stopped"
- Account: "cannot login", "account blocked", "account access"
- General complaints: "not happy", "complaint", "poor quality", "order missing", "package missing"
- Tickets: "my tickets", "show tickets", "raised a ticket"
- CRITICAL: "my order is missing" → support_query (it's a complaint, NOT an order tracking query)
- CRITICAL: "i haven't received my order" → support_query (complaint about non-delivery)
- CRITICAL: "order is damaged/broken/wrong" → support_query

**out_of_scope** — user is asking about something completely unrelated to shopping, orders, or support.
Examples:
- "what is the weather", "tell me a joke", "write a poem", "cricket score"
- "who is the president", "stock market today", "translate this text"
- "what is 2+2", "write an essay", "news today"

User message: "{state['current_input']}"

Key rules:
- "cancel my order" / "cancel order" / "want to cancel" → support_query (cancellation = support action)
- "return my order" / "want to return" → support_query (return = support action)
- "show my orders" / "track order" / "where is my order" → order_query (viewing/tracking = order)
- "show me [product]" / "find me [product]" / "recommend [product]" → product_query (shopping)
- anything unrelated to shopping/orders/support → out_of_scope

Return only the intent label. Nothing else."""

    try:
        structured = llm.with_structured_output(IntentOutput)
        result = structured.invoke(prompt)
        intent = result.intent
    except Exception as e:
        log.error(f"Router failed: {e}")
        intent = "order_query"

    log.info(f"Intent classified: {intent}")
    return {**state, "intent": intent}


def handle_out_of_scope(state: AgentState) -> AgentState:
    return {
        **state,
        "response": (
            "I'm sorry, I don't have knowledge about that yet. "
            "I'm here to help you with:\n\n"
            "- 📦 **Orders** — track deliveries, check status, view order history\n"
            "- 🛍️ **Products** — find, search, or get recommendations from our catalog\n"
            "- 🎧 **Support** — complaints, refunds, returns, warranty claims\n\n"
            "What can I help you with today?"
        ),
    }


def route_to_agent(state: AgentState) -> str:
    return state.get("intent", "support_query")


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

    graph.add_node("intent_router", intent_router)
    graph.add_node("order_agent", run_order_agent)
    graph.add_node("product_agent", run_product_agent)
    graph.add_node("support_agent", run_support_agent)
    graph.add_node("out_of_scope", handle_out_of_scope)

    graph.set_entry_point("intent_router")

    graph.add_conditional_edges(
        "intent_router",
        route_to_agent,
        {
            "order_query": "order_agent",
            "product_query": "product_agent",
            "support_query": "support_agent",
            "out_of_scope": "out_of_scope",
        },
    )

    graph.add_edge("order_agent", END)
    graph.add_edge("product_agent", END)
    graph.add_edge("support_agent", END)
    graph.add_edge("out_of_scope", END)

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
            session_id=session_id,
            user_id="test-user",
            request_id=str(uuid.uuid4()),
            messages=[],
            current_input=msg,
        )
        result = pipeline.invoke(state)
        print(f"Intent:   {result['intent']}")
        print(f"Response: {result.get('response', 'No response')[:150]}")
