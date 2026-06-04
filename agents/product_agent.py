import re
import logging
import json as _json
import mlflow
import psycopg2
import psycopg2.extras
from langgraph.graph import StateGraph, END

from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import calculate_cost, log_llm_span, log_tool_span
from database import get_conn, save_message
from agents.product_constants import _CATEGORY_NORM, BRAND_MAP, _GENERIC_WORDS, _CARRY_PRODUCT_TYPES

_log = logging.getLogger(__name__)

llm = __import__("langchain_groq").ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)


# ── Database search (PostgreSQL full-text search) ─────────────────────────────


def mock_product_api_call(prefs: dict, retry: int = 0) -> list:
    """Search products using PostgreSQL full-text search on the search_vector column."""
    search_query = prefs.get("search_query") or ""

    # Progressive broadening on retry — simplify to the main noun on retry 1.
    # Never clear search_query entirely: returning all products when the user asked
    # for something specific (e.g. "HP bags") produces completely wrong results.
    if retry == 1 and search_query:
        words = search_query.split()
        search_query = words[-1] if words else search_query

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                conditions = ["availability = TRUE"]
                where_params: list = []

                if search_query:
                    conditions.append("search_vector @@ plainto_tsquery('english', %s)")
                    where_params.append(search_query)

                if prefs.get("category"):
                    conditions.append("category ILIKE %s")
                    where_params.append(f"%{prefs['category']}%")

                if prefs.get("max_price"):
                    conditions.append("price <= %s")
                    where_params.append(float(prefs["max_price"]))

                if prefs.get("min_price"):
                    conditions.append("price >= %s")
                    where_params.append(float(prefs["min_price"]))

                if prefs.get("min_rating"):
                    conditions.append("rating >= %s")
                    where_params.append(float(prefs["min_rating"]))

                if prefs.get("max_rating"):
                    conditions.append("rating < %s")
                    where_params.append(float(prefs["max_rating"]))

                if prefs.get("brand"):
                    conditions.append("brand ILIKE %s")
                    where_params.append(f"%{prefs['brand']}%")

                where = " AND ".join(conditions)
                user_limit = prefs.get("limit", 5)
                fetch_limit = max(user_limit * 4, 20)

                sort_by = prefs.get("sort_by", "relevance")
                order_params: list = []

                if sort_by == "price_asc":
                    order_clause = "price ASC NULLS LAST, rating DESC NULLS LAST"
                elif sort_by == "price_desc":
                    order_clause = "price DESC NULLS LAST, rating DESC NULLS LAST"
                elif sort_by == "rating":
                    order_clause = "rating DESC NULLS LAST"
                elif sort_by == "new":
                    order_clause = "created_at DESC NULLS LAST, rating DESC NULLS LAST"
                else:
                    if search_query:
                        order_clause = (
                            "ts_rank(search_vector, plainto_tsquery('english', %s)) DESC, " "rating DESC NULLS LAST"
                        )
                        order_params = [search_query]
                    else:
                        order_clause = "rating DESC NULLS LAST"

                query = (
                    "SELECT product_id, name, category, brand, price, original_price, "
                    "discount_pct, rating, rating_count, description, availability "
                    f"FROM products WHERE {where} ORDER BY {order_clause} LIMIT %s"
                )
                all_params = where_params + order_params + [fetch_limit]

                _log.debug("FTS query: %s | params: %s", query, all_params)
                cur.execute(query, all_params)
                return [dict(r) for r in cur.fetchall()]

    except Exception as e:
        _log.error("Product DB query failed: %s", e)
        return []


# ── Comparison & brands helpers ───────────────────────────────────────────────


def _fetch_single_product(search_query: str) -> dict | None:
    """Return the single best FTS match for a product query."""
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT product_id, name, brand, category, price, original_price,
                              discount_pct, rating, rating_count, description
                       FROM products
                       WHERE availability = TRUE
                         AND search_vector @@ plainto_tsquery('english', %s)
                       ORDER BY ts_rank(search_vector, plainto_tsquery('english', %s)) DESC,
                                rating DESC NULLS LAST
                       LIMIT 1""",
                    [search_query, search_query],
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        _log.error("Single product fetch error: %s", e)
        return None


def _handle_comparison(state: AgentState) -> AgentState:
    """Handle 'compare X vs Y' — fetch both, LLM recommends one."""
    log = get_log(state["request_id"], "product_agent", "comparison")
    log.info("Comparison query detected")
    msg = state["current_input"]
    msg_lower = msg.lower()

    # Parse the two sides of the comparison
    parts = None
    for sep in [r"\bvs\.?\b", r"\bversus\b"]:
        split = re.split(sep, msg_lower, maxsplit=1)
        if len(split) == 2:
            parts = split
            break
    if not parts:
        m = re.match(r"compare\s+(.+?)\s+(?:and|with|or)\s+(.+)", msg_lower)
        if m:
            parts = [m.group(1), m.group(2)]
    if not parts:
        m = re.search(r"(?:which.*better|better.*which|between)\s+(.+?)\s+or\s+(.+)", msg_lower)
        if m:
            parts = [m.group(1), m.group(2)]

    if not parts:
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                "I'd love to help you compare! Please phrase it like:\n\n"
                '*"Compare Sony WH-1000XM5 vs Bose QC45"*\n'
                '*"Samsung Galaxy S24 vs iPhone 15 — which is better?"*'
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # Clean up filler words
    _FILLER = {"compare", "the", "a", "an", "show", "me", "which", "is", "better", "between"}

    def _clean(s):
        return " ".join(w for w in s.strip().split() if w not in _FILLER)

    q1, q2 = _clean(parts[0]), _clean(parts[1])
    p1, p2 = _fetch_single_product(q1), _fetch_single_product(q2)

    if not p1 and not p2:
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": f"I couldn't find **{q1}** or **{q2}** in our catalog.",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }
    if not p1:
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                f"I couldn't find **{q1}** in our catalog.\n\n" f"Did you mean to search for **{p2['name']}** instead?"
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }
    if not p2:
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                f"I couldn't find **{q2}** in our catalog.\n\n" f"Did you mean to search for **{p1['name']}** instead?"
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # Both found — LLM comparison + recommendation
    prompt = (
        f"Compare these two products and recommend ONE. Be concise.\n\n"
        f"**Product 1:** {p1['name']}\n"
        f"- Price: ₹{p1.get('price', 'N/A')} | Rating: {p1.get('rating', 'N/A')}/5 ({p1.get('rating_count', 'N/A')} reviews)\n"
        f"- {(p1.get('description') or '')[:250]}\n\n"
        f"**Product 2:** {p2['name']}\n"
        f"- Price: ₹{p2.get('price', 'N/A')} | Rating: {p2.get('rating', 'N/A')}/5 ({p2.get('rating_count', 'N/A')} reviews)\n"
        f"- {(p2.get('description') or '')[:250]}\n\n"
        f'User asked: "{msg}"\n\n'
        f"Format your response exactly like this:\n"
        f"**{p1['name'][:50]}**\n• [2-3 key strengths]\n\n"
        f"**{p2['name'][:50]}**\n• [2-3 key strengths]\n\n"
        f"**Our Pick: [winner name]** — [one sentence explaining why]"
    )

    try:
        resp = llm.invoke(prompt)
        usage = resp.usage_metadata or {}
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cost = calculate_cost(config.LLM_MODEL, in_tok, out_tok)
        response = resp.content.strip()
    except Exception as e:
        log.error(f"Comparison LLM failed: {e}")
        winner = p1 if (p1.get("rating") or 0) >= (p2.get("rating") or 0) else p2
        response = (
            f"**{p1['name'][:60]}** — ₹{p1.get('price')} | {p1.get('rating')}/5\n\n"
            f"**{p2['name'][:60]}** — ₹{p2.get('price')} | {p2.get('rating')}/5\n\n"
            f"**Our Pick: {winner['name'][:50]}** — higher rated at {winner.get('rating')}/5."
        )
        in_tok = out_tok = 0
        cost = 0.0

    log.info(f"Compared: {p1['name'][:30]} vs {p2['name'][:30]}")
    return {
        **state,
        "search_preferences": None,
        "search_retry": 0,
        "response": response,
        "total_tokens": state.get("total_tokens", 0) + in_tok + out_tok,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + cost,
    }


def _handle_brands_listing(state: AgentState) -> AgentState:
    """Return available brands grouped by category, with a suggestion to pick one."""
    log = get_log(state["request_id"], "product_agent", "brands_listing")
    log.info("Brands listing query detected")

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT brand, category, COUNT(*) AS cnt
                       FROM products
                       WHERE availability = TRUE AND brand IS NOT NULL
                       GROUP BY brand, category
                       ORDER BY category, cnt DESC""",
                )
                rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        log.error(f"Brands query failed: {e}")
        rows = []

    if not rows:
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": "I couldn't fetch the brand list right now. Please try again.",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    by_cat: dict = {}
    for r in rows:
        cat = r["category"] or "Other"
        by_cat.setdefault(cat, []).append(r["brand"])

    _ICONS = {"Electronics": "📱", "Computers&Accessories": "💻", "Home&Kitchen": "🏠"}
    lines = ["Here are all brands available in our catalog:\n"]
    for cat, brands in by_cat.items():
        lines.append(f"{_ICONS.get(cat, '•')} **{cat}**")
        lines.append(", ".join(brands))
        lines.append("")
    lines.append("Which brand are you interested in? I can show their products!")

    return {
        **state,
        "search_preferences": None,
        "search_retry": 0,
        "response": "\n".join(lines),
        "total_tokens": state.get("total_tokens", 0),
        "total_cost_usd": state.get("total_cost_usd", 0.0),
    }


# ── Agent nodes ────────────────────────────────────────────────────────────────


def extract_preferences(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "extract_preferences")
    log.info("Node entered")

    msg = state["current_input"]
    msg_lower = msg.lower()

    # ── Greetings ─────────────────────────────────────────
    _GREETING_PATTERNS = [
        r"^hi\b",
        r"^hello\b",
        r"^hey\b",
        r"\bwho are you\b",
        r"\bwhat can you do\b",
        r"\bwhat do you do\b",
        r"\bintroduce yourself\b",
    ]
    if any(re.search(p, msg_lower) for p in _GREETING_PATTERNS):
        log.info("Greeting detected")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                "Hi! I'm your product assistant. I can help you find:\n\n"
                "- **Electronics** — phones, earbuds, headphones, TVs, ACs\n"
                "- **Computers & Accessories** — laptops, keyboards, mice, monitors\n"
                "- **Home & Kitchen** — mixer grinders, air fryers, pressure cookers\n\n"
                "Tell me what you're looking for!\n"
                'Example: *"Sony wireless headphones under ₹5000"*'
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # ── Browse-all / catalogue intent ────────────────────
    _BROWSE_PATTERNS = [
        r"\bshow\s+(me\s+)?all\s+products?\b",
        r"\bwhat\s+(products?\s+)?do\s+you\s+(have|sell|offer)\b",
        r"\bwhat\s+can\s+i\s+buy\b",
        r"\bbrowse\s+(all\s+)?products?\b",
        r"\bwhat\s+(is\s+)?available\b",
        r"\blist\s+all\s+products?\b",
        r"\bshow\s+me\s+everything\b",
    ]
    if any(re.search(p, msg_lower) for p in _BROWSE_PATTERNS):
        log.info("Browse-all detected — returning category overview")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                "Here's what I can help you find:\n\n"
                "📱 **Electronics** — Phones, Smart TVs, ACs, Refrigerators, Washing Machines\n"
                "💻 **Computers & Accessories** — Laptops, Keyboards, Mice, Monitors, Webcams, SSDs\n"
                "🎧 **Audio** — Headphones, Earbuds, Earphones, Neckbands, Speakers, Soundbars\n"
                "🏠 **Home & Kitchen** — Mixer Grinders, Air Fryers, Pressure Cookers, "
                "Microwaves, Water Purifiers\n\n"
                "Popular brands: Apple, Samsung, Sony, Dell, Lenovo, HP, boAt, Logitech, Prestige and more.\n\n"
                "Just tell me what you need! Examples:\n"
                '- *"Sony headphones under ₹5000"*\n'
                '- *"Cheapest laptop under ₹40000"*\n'
                '- *"Best rated mixer grinder"*'
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    # ── Comparison intent ─────────────────────────────────
    _COMPARE_PATTERNS = [
        r"\bcompare\b",
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\bwhich.*(?:better|should i buy|is good)\b",
        r"\b(?:better|difference)\s+between\b",
    ]
    if any(re.search(p, msg_lower) for p in _COMPARE_PATTERNS):
        return _handle_comparison(state)

    # ── Brands listing intent ─────────────────────────────
    _BRANDS_PATTERNS = [
        r"\bwhat brands?\b",
        r"\bwhich brands?\b",
        r"\bshow.*brands?\b",
        r"\blist.*brands?\b",
        r"\bavailable brands?\b",
        r"\bbrands? (do )?you (have|carry|sell|offer)\b",
        r"\bwhat brands? are (there|available)\b",
    ]
    if any(re.search(p, msg_lower) for p in _BRANDS_PATTERNS):
        return _handle_brands_listing(state)

    recent_msgs = state.get("messages", [])[-2:]
    history_lines = []
    for m in recent_msgs:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "").replace("\n", " ").strip()[:80]
        history_lines.append(f"{role}: {content}")
    history_snippet = "\n".join(history_lines) if history_lines else "None"

    extraction_prompt = f"""Extract product search preferences from the user message. Return ONLY JSON.

Recent conversation:
{history_snippet}

User: "{msg}"

JSON format:
{{"search_query":null,"brand":null,"category":null,"max_price":null,"min_price":null,"min_rating":null,"max_rating":null,"sort_by":"relevance","limit":5}}

Rules:
- search_query: the product the user wants as a short descriptive phrase.
  Keep meaningful attributes: "wireless mouse", "noise cancelling headphone", "gaming laptop", "mixer grinder".
  Context mappings: "for commute/gym/workout/running" → "earbuds", "for studying/office/calls" → "headphone",
  "for coffee" → "coffee maker", "for cooking/kitchen" → "mixer grinder", "for home office" → "monitor".
  Set null ONLY if no product is implied (pure price/rating filter with zero product context).
- brand: only if the user explicitly names a brand (Samsung, Sony, Logitech, boAt, etc.).
- category: "Electronics" for phones/TVs/ACs/earbuds/headphones/cameras/smartwatches/refrigerators/washing machines.
  "Computers&Accessories" for laptops/keyboards/mice/monitors/printers/SSDs/webcams.
  "Home&Kitchen" for kitchen appliances, water bottles, pressure cookers.
  null if multiple categories or unclear.
- max_price: numeric for "under/below/within/less than ₹X".
- min_price: numeric for "above/over/more than ₹X".
- min_rating: numeric for "rated above X" or "X stars and above".
- max_rating: numeric for "rated below X".
- sort_by: "price_asc" if cheapest/budget/lowest price/most affordable, "price_desc" if most expensive/premium,
  "rating" if best rated/top rated, "new" if new arrivals/latest/newest/just launched/recently added,
  "relevance" (default for everything else).
- limit: number if user says "top N" or "best N". "all/show all" → 10. Default 5.
- FOLLOW-UP: if the message is a short refinement ("only boAt", "under 2000", "show cheaper"),
  carry the product type from recent conversation into search_query.

Return ONLY valid JSON."""

    try:
        response = llm.invoke(extraction_prompt)
        text = response.content.strip()
        if "```" in text:
            for part in text.split("```"):
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
            span_name="extract_preferences",
            prompt_text=extraction_prompt,
            response_text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=config.LLM_MODEL,
            prompt_name="extract_preferences",
            prompt_version=1,
            trace_id=state.get("mlflow_trace_id"),
            parent_id=state.get("mlflow_span_id"),
        )

    except Exception as e:
        log.error(f"LLM extraction failed: {e}")
        extracted = {
            "search_query": None,
            "brand": None,
            "category": None,
            "max_price": None,
            "min_price": None,
            "min_rating": None,
            "max_rating": None,
            "sort_by": "relevance",
            "limit": 5,
        }
        input_tokens = 0
        output_tokens = 0
        cost = 0.0

    raw_cat = extracted.get("category")
    category = _CATEGORY_NORM.get(raw_cat.lower().strip(), None) if raw_cat else None

    prefs = {
        "search_query": extracted.get("search_query") or None,
        "brand": extracted.get("brand"),
        "category": category,
        "max_price": extracted.get("max_price"),
        "min_price": extracted.get("min_price"),
        "min_rating": extracted.get("min_rating"),
        "max_rating": extracted.get("max_rating"),
        "sort_by": extracted.get("sort_by") or "relevance",
        "limit": extracted.get("limit", 5),
    }

    # Fallback LLM when no search_query was extracted
    if not prefs["search_query"]:
        fallback_prompt = (
            f"What specific product is the user asking about? "
            f"Reply with ONLY the product name/type — nothing else.\n\n"
            f'User: "{msg}"\n\n'
            f'Examples: "wireless mouse", "gaming laptop", "mixer grinder", "air fryer"\n'
            f"If truly no product is implied, reply: none"
        )
        try:
            fb = llm.invoke(fallback_prompt)
            fb_usage = fb.usage_metadata or {}
            fb_in = fb_usage.get("input_tokens", 0)
            fb_out = fb_usage.get("output_tokens", 0)
            fb_cost = calculate_cost(config.LLM_MODEL, fb_in, fb_out)
            keyword = fb.content.strip().lower().strip("\"'")
            if keyword and keyword not in _GENERIC_WORDS:
                prefs["search_query"] = keyword
                log.info(f"Fallback search_query: {keyword}")
            input_tokens += fb_in
            output_tokens += fb_out
            cost += fb_cost
        except Exception as e:
            log.error(f"Fallback LLM failed: {e}")

    # ── Regex fallbacks ────────────────────────────────────

    if prefs.get("sort_by", "relevance") == "relevance":
        if re.search(r"\b(cheapest|most\s+affordable|lowest\s+price|budget)\b", msg_lower):
            prefs["sort_by"] = "price_asc"
        elif re.search(r"\b(most\s+expensive|highest\s+price|premium|costliest)\b", msg_lower):
            prefs["sort_by"] = "price_desc"
        elif re.search(
            r"\b(new arrivals?|latest|newest|just\s+(launched|added|in)|recently\s+(added|launched)|what'?s?\s+new)\b",
            msg_lower,
        ):
            prefs["sort_by"] = "new"

    if not prefs.get("min_rating"):
        # Pattern A: "X stars/rating and above" — number comes BEFORE the keyword
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:star|rating)s?\s*(?:and\s+)?(?:above|over|plus|\+)",
            msg_lower,
        )
        if m:
            prefs["min_rating"] = float(m.group(1))
        else:
            # Pattern B: "above/over/at least X [stars/rating]" — keyword comes FIRST.
            # Use finditer and skip values > 5 so "above 2000" is never confused with
            # a rating when the message also says "above 4.5 ratings".
            # NOTE: requires \s+ between keyword and number (pattern was previously
            # missing this, causing "above 4.5" to never match).
            for match in re.finditer(
                r"(?:above|over|minimum|at least|rated?)\s+(\d+(?:\.\d+)?)\s*(?:star|rating)s?",
                msg_lower,
            ):
                val = float(match.group(1))
                if 0 < val <= 5:
                    prefs["min_rating"] = val
                    break

    if not prefs.get("max_rating"):
        # Pattern A: "X stars/rating and below"
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:star|rating)s?\s*(?:and\s+)?(?:below|under)",
            msg_lower,
        )
        if m:
            prefs["max_rating"] = float(m.group(1))
        else:
            # Pattern B: "below/under X [stars/rating]" — same guard: only accept ≤ 5
            for match in re.finditer(
                r"(?:below|under|less than|max(?:imum)?)\s+(\d+(?:\.\d+)?)\s*(?:star|rating)s?",
                msg_lower,
            ):
                val = float(match.group(1))
                if 0 < val <= 5:
                    prefs["max_rating"] = val
                    break

    if not prefs.get("max_price"):
        m = re.search(
            r"(?:below|under|less than|max(?:imum)?)\s+"
            r"(?:rs\.?\s*|₹\s*|inr\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rs\.?|₹|rupees?|inr)\b",
            msg_lower,
        )
        if not m:
            m = re.search(r"(?:below|under|less than)\s+(\d{3,}(?:,\d+)*(?:\.\d+)?)\b", msg_lower)
        if m:
            prefs["max_price"] = float(m.group(1).replace(",", ""))

    if not prefs.get("min_price"):
        m = re.search(
            r"(?:above|over|minimum|at least|more than)\s+"
            r"(?:rs\.?\s*|₹\s*|inr\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rs\.?|₹|rupees?|inr)\b",
            msg_lower,
        )
        if not m:
            m = re.search(r"(?:above|over|more than)\s+(\d{3,}(?:,\d+)*(?:\.\d+)?)\b", msg_lower)
        if m:
            prefs["min_price"] = float(m.group(1).replace(",", ""))

    if re.search(r"\b(all|every|complete list)\b", msg_lower):
        prefs["limit"] = max(prefs.get("limit", 5), 10)

    # Brand fallback: scan message for known brands
    if not prefs.get("brand"):
        for token, display in BRAND_MAP.items():
            if re.search(rf"\b{re.escape(token)}\b", msg_lower):
                prefs["brand"] = display
                break

    # ── Carry-forward from conversation history ───────────
    # Fires when the current message looks like a refinement of the previous search.
    # Two trigger conditions:
    #   1. Has a price/rating filter but no product type (e.g. "above 40000")
    #   2. Is a short modifier message ≤4 words (e.g. "only hp", "just Samsung")
    _has_filter = prefs.get("max_price") or prefs.get("min_price") or prefs.get("min_rating") or prefs.get("max_rating")
    _is_refinement = _has_filter or len(msg.strip().split()) <= 4

    if _is_refinement and recent_msgs:
        for hist_m in reversed(recent_msgs):
            hist_content = (hist_m.get("content") or "").lower()

            # Carry forward brand when not set in current turn.
            # Only carry it when we're still in the same product context:
            # check that at least one word from current search_query appears in the
            # history message (prevents "find me a mouse" from inheriting Dell from
            # a previous laptop search).
            if not prefs.get("brand"):
                sq = prefs.get("search_query") or ""
                sq_words = [w for w in sq.split() if len(w) > 2]
                same_context = not sq_words or any(re.search(rf"\b{re.escape(w)}\b", hist_content) for w in sq_words)
                if same_context:
                    for token, display in BRAND_MAP.items():
                        if re.search(rf"\b{re.escape(token)}\b", hist_content):
                            prefs["brand"] = display
                            log.info(f"Carried forward brand: {display}")
                            break

            # Carry forward search_query only when not already set
            if not prefs.get("search_query"):
                for pt in _CARRY_PRODUCT_TYPES:
                    if re.search(rf"\b{re.escape(pt)}\b", hist_content):
                        prefs["search_query"] = pt
                        log.info(f"Carried forward search_query: {pt}")
                        break

            if prefs.get("brand") and prefs.get("search_query"):
                break

    log_tool_span(
        span_name="extract_preferences",
        tool_name="preference_extractor",
        tool_input={"message": state["current_input"]},
        tool_output={"prefs": str(prefs)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )
    log.info(f"Preferences extracted: {prefs}")

    # ── No searchable signal — ask for clarification ───────
    no_signal = (
        not prefs.get("search_query")
        and not prefs.get("brand")
        and not prefs.get("category")
        and not prefs.get("max_price")
        and not prefs.get("min_price")
    )
    if no_signal:
        log.info("No searchable signal — returning clarification request")
        return {
            **state,
            "search_preferences": prefs,
            "search_retry": 0,
            "response": (
                "I can help you find the perfect product! Please tell me:\n\n"
                "- **What product** are you looking for? (e.g. laptop, headphones, TV)\n"
                "- Your **budget**? (optional)\n"
                "- Any **brand** preference? (optional)\n\n"
                'Example: *"Show me Sony headphones under ₹5000"*'
            ),
            "total_tokens": state.get("total_tokens", 0) + input_tokens + output_tokens,
            "total_cost_usd": state.get("total_cost_usd", 0.0) + cost,
        }

    return {
        **state,
        "search_preferences": prefs,
        "search_retry": 0,
        "total_tokens": state.get("total_tokens", 0) + input_tokens + output_tokens,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + cost,
    }


def extract_preferences_edge(state: AgentState) -> str:
    if state.get("response"):
        return "save_to_db"
    return "search_products"


def search_products(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "search_products")
    log.info("Tool called: search_products")

    prefs = state.get("search_preferences", {})
    retry = state.get("search_retry", 0)
    results = mock_product_api_call(prefs, retry)

    log_tool_span(
        span_name="search_products",
        tool_name="product_catalog_db",
        tool_input={"prefs": str(prefs), "retry": retry},
        tool_output={"results_count": len(results)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )
    log.info(f"Found {len(results)} products")
    return {**state, "search_results": results}


def results_found_edge(state: AgentState) -> str:
    results = state.get("search_results", [])
    retry = state.get("search_retry", 0)
    if results:
        return "rank_and_filter"
    if retry < 2:
        return "broaden_search"
    return "no_results_response"


def broaden_search(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "broaden_search")
    prefs = state.get("search_preferences", {})
    retry = state.get("search_retry", 0)

    if retry == 0:
        prefs = {**prefs, "brand": None}
    elif retry == 1:
        sq = prefs.get("search_query") or ""
        if sq:
            words = sq.split()
            prefs = {**prefs, "search_query": words[-1] if words else sq}
        if prefs.get("max_price"):
            prefs = {**prefs, "max_price": prefs["max_price"] * 1.5}
        prefs = {**prefs, "category": None}

    log.info(f"Broadening search (retry {retry + 1}): {prefs}")
    return {**state, "search_preferences": prefs, "search_retry": retry + 1}


def no_results_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "no_results_response")
    log.warning("No products found after retries")

    sq = (state.get("search_preferences") or {}).get("search_query") or ""

    # Re-read the original user message to recover the brand — by the time we reach
    # this node, broaden_search has already stripped brand from search_preferences.
    original_brand = None
    msg_lower = state["current_input"].lower()
    for token, display in BRAND_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", msg_lower):
            original_brand = display
            break

    if original_brand and sq:
        response = (
            f"**{original_brand}** doesn't carry **{sq}** in our catalog.\n\n"
            f'Try *"show me {sq}"* to see options from all brands, '
            f'or *"show me {original_brand} products"* to browse what {original_brand} offers.'
        )
    elif sq:
        response = (
            f"I couldn't find any **{sq}** matching your requirements.\n\n"
            "Try adjusting your filters or searching with different terms."
        )
    else:
        response = (
            "I couldn't find any products matching your requirements.\n\n"
            "Try a broader search term or remove some filters."
        )

    log.info(f"No results: sq={sq!r} original_brand={original_brand!r}")
    return {**state, "response": response}


def rank_and_filter(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "rank_and_filter")
    log.info("LLM called")

    results = state.get("search_results", [])
    user_limit = state.get("search_preferences", {}).get("limit", 5)
    pool_size = max(user_limit * 2, 6)
    pool = results[:pool_size]

    products_text = "\n".join(
        [f"{i+1}. {p['name']} | Price: ₹{p['price']} | Rating: {p['rating']}" for i, p in enumerate(pool)]
    )

    prompt_template = mlflow.genai.load_prompt("prompts:/product_ranking_prompt/1")
    prompt = prompt_template.format(
        user_request=state["current_input"],
        products_text=products_text,
    )

    try:
        response = llm.invoke(prompt)
        usage = response.usage_metadata or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        try:
            order = [int(x.strip()) - 1 for x in response.content.strip().split(",")]
            ranked = [pool[i] for i in order if i < len(pool)]
        except Exception:
            ranked = pool
    except Exception as e:
        log.warning(f"LLM ranking failed: {e}")
        ranked = pool
        cost = 0.0
        input_tokens = 0
        output_tokens = 0
        response = type("R", (), {"content": ""})()

    log_llm_span(
        span_name="rank_and_filter",
        prompt_text=prompt,
        response_text=response.content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=config.LLM_MODEL,
        prompt_name="product_ranking_prompt",
        prompt_version=1,
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Products ranked: {len(ranked)}")
    return {
        **state,
        "ranked_products": ranked,
        "total_tokens": state["total_tokens"] + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def fetch_reviews(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "fetch_reviews")
    products = state.get("ranked_products", [])
    enriched = list(products)

    try:
        product_ids = [p["product_id"] for p in products]
        if product_ids:
            with get_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """SELECT product_id, review_title, review_text, rating
                           FROM reviews WHERE product_id = ANY(%s)
                           ORDER BY rating DESC""",
                        [product_ids],
                    )
                    reviews_by_id: dict = {}
                    for row in cur.fetchall():
                        pid = row["product_id"]
                        if pid not in reviews_by_id:
                            reviews_by_id[pid] = []
                        if len(reviews_by_id[pid]) < 3:
                            reviews_by_id[pid].append(dict(row))
            enriched = [{**p, "reviews": reviews_by_id.get(p["product_id"], [])} for p in products]
    except Exception as e:
        log.error(f"Reviews fetch error: {e}")

    log_tool_span(
        span_name="fetch_reviews",
        tool_name="reviews_table",
        tool_input={"product_count": len(products)},
        tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )
    log.info(f"Fetched reviews for {len(enriched)} products")
    return {**state, "enriched_products": enriched}


def fetch_specs(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "fetch_specs")
    products = state.get("enriched_products", [])
    enriched = list(products)

    try:
        product_ids = [p["product_id"] for p in products]
        if product_ids:
            with get_conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """SELECT product_id, description, rating, rating_count,
                                  discount_pct, original_price
                           FROM products WHERE product_id = ANY(%s)""",
                        [product_ids],
                    )
                    specs_by_id = {row["product_id"]: dict(row) for row in cur.fetchall()}
            enriched = [{**p, "specs": specs_by_id.get(p["product_id"], {})} for p in products]
    except Exception as e:
        log.error(f"Specs fetch error: {e}")

    log_tool_span(
        span_name="fetch_specs",
        tool_name="products_specs",
        tool_input={"product_count": len(products)},
        tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"),
        parent_id=state.get("mlflow_span_id"),
    )
    log.info(f"Fetched specs for {len(enriched)} products")
    return {**state, "enriched_products": enriched}


def compute_score(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "compute_score")
    products = state.get("enriched_products", [])
    scored = []

    for p in products:
        rating = float(p.get("rating") or 0)
        review_count = len(p.get("reviews", []))
        price = float(p.get("price") or 9999)
        orig_price = float(p.get("original_price") or price)
        discount = ((orig_price - price) / orig_price * 100) if orig_price > 0 else 0
        score = (rating / 5 * 40) + (min(review_count, 3) / 3 * 30) + (min(discount, 50) / 50 * 30)
        scored.append({**p, "score": round(score, 2)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"Scored {len(scored)} products")
    return {**state, "enriched_products": scored}


def build_product_enrichment_subgraph():
    sub = StateGraph(AgentState)
    sub.add_node("fetch_reviews", fetch_reviews)
    sub.add_node("fetch_specs", fetch_specs)
    sub.add_node("compute_score", compute_score)
    sub.set_entry_point("fetch_reviews")
    sub.add_edge("fetch_reviews", "fetch_specs")
    sub.add_edge("fetch_specs", "compute_score")
    sub.add_edge("compute_score", END)
    return sub.compile()


def _extract_why(desc: str) -> str:
    first = re.split(r"(?<=[.!])\s+", desc.strip())[0].strip()
    if len(first) >= 20:
        return first[:160] + ("…" if len(first) > 160 else "")
    return desc[:160] + ("…" if len(desc) > 160 else "")


def format_recommendations(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "format_recommendations")
    log.info("Node entered")

    search_prefs = state.get("search_preferences") or {}
    limit = search_prefs.get("limit", 3)
    products = state.get("enriched_products", [])[:limit]
    if not products:
        return {**state, "response": "No products found matching your criteria."}

    search_query = search_prefs.get("search_query") or "product"
    lines = [f"Here are the top **{search_query}** recommendations:\n"]

    for i, p in enumerate(products, 1):
        price = f"₹{p['price']}" if p.get("price") is not None else "Price unavailable"
        rating = f"{p['rating']}/5" if p.get("rating") is not None else "No rating"
        specs = p.get("specs") or {}
        desc = (specs.get("description") or p.get("description") or "").strip()
        why = _extract_why(desc) if desc else "Highly rated option in its category."

        lines.append(f"### {i}. {p['name']}")
        lines.append(f"- **Price:** {price}")
        lines.append(f"- **Rating:** {rating}")
        lines.append(f"- **Why buy it:** {why}")
        lines.append("")

    if len(products) >= 2:
        sort_by = search_prefs.get("sort_by", "relevance")
        if sort_by == "price_asc":
            best = min(products, key=lambda x: x.get("price") or float("inf"))
            lines.append(f"**{best['name'][:60]}** is the most affordable option here.")
        else:
            cheapest = min(products, key=lambda x: x.get("price") or float("inf"))
            top_rated = max(products, key=lambda x: x.get("rating") or 0)
            if cheapest["product_id"] != top_rated["product_id"]:
                lines.append(
                    f"Pick **{cheapest['name'][:45]}** for the best value, "
                    f"or **{top_rated['name'][:45]}** for the highest-rated option."
                )
            else:
                lines.append(f"**{top_rated['name'][:60]}** offers the best mix of value and quality.")

    log.info("Recommendations formatted")
    return {
        **state,
        "response": "\n".join(lines),
        "total_tokens": state["total_tokens"],
        "total_cost_usd": state["total_cost_usd"],
    }


def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "save_to_db")
    log.info("Saving response to DB")
    with mlflow.start_span(name="save_to_db", span_type="TOOL") as span:
        span.set_inputs({"session_id": state["session_id"], "role": "assistant"})
        save_message(
            session_id=state["session_id"],
            role="assistant",
            content=state["response"],
            agent_name="product_agent",
            token_usage={
                "total_tokens": state["total_tokens"],
                "total_cost_usd": state["total_cost_usd"],
            },
            mlflow_run_id=state.get("mlflow_run_id"),
        )
        span.set_outputs({"status": "saved"})
    log.info("Response saved")
    return state


# ── Graph assembly ─────────────────────────────────────────────────────────────


def build_product_agent():
    graph = StateGraph(AgentState)

    graph.add_node("extract_preferences", extract_preferences)
    graph.add_node("search_products", search_products)
    graph.add_node("broaden_search", broaden_search)
    graph.add_node("rank_and_filter", rank_and_filter)
    graph.add_node("product_enrichment", build_product_enrichment_subgraph())
    graph.add_node("format_recommendations", format_recommendations)
    graph.add_node("no_results_response", no_results_response)
    graph.add_node("save_to_db", save_to_db)

    graph.set_entry_point("extract_preferences")

    graph.add_conditional_edges(
        "extract_preferences",
        extract_preferences_edge,
        {"search_products": "search_products", "save_to_db": "save_to_db"},
    )

    graph.add_conditional_edges(
        "search_products",
        results_found_edge,
        {
            "rank_and_filter": "rank_and_filter",
            "broaden_search": "broaden_search",
            "no_results_response": "no_results_response",
        },
    )

    graph.add_edge("broaden_search", "search_products")
    graph.add_edge("rank_and_filter", "product_enrichment")
    graph.add_edge("product_enrichment", "format_recommendations")
    graph.add_edge("format_recommendations", "save_to_db")
    graph.add_edge("no_results_response", "save_to_db")
    graph.add_edge("save_to_db", END)

    return graph.compile()


product_agent = build_product_agent()


if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    for query in [
        "find me a good laptop under 60000",
        "cheapest wireless mouse",
        "Sony noise cancelling headphones",
        "best rated mixer grinder under 3000",
    ]:
        state = empty_state(
            session_id=session_id,
            user_id="test-user",
            request_id="test-req-002",
            messages=[],
            current_input=query,
        )
        result = product_agent.invoke(state)
        print(f"\n[{query}]\n{result['response'][:200]}")
