import re
import uuid
import hashlib
import logging
import json as _json
import mlflow
import psycopg2
import psycopg2.extras
from typing import Optional, List
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode

from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import calculate_cost, log_llm_span, log_tool_span
from database import get_conn, save_message
from agents.product_constants import _CATEGORY_NORM, BRAND_MAP, _GENERIC_WORDS, _CARRY_PRODUCT_TYPES

_log = logging.getLogger(__name__)

# ── Redis cache (lazy, falls back gracefully if unavailable) ──────────────────
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as _redis
            client = _redis.Redis(
                host=getattr(config, "REDIS_HOST", "redis"),
                port=int(getattr(config, "REDIS_PORT", 6379)),
                decode_responses=True,
                socket_connect_timeout=1,
            )
            client.ping()
            _redis_client = client
            _log.info("Redis connected")
        except Exception as e:
            _log.warning(f"Redis unavailable, caching disabled: {e}")
            _redis_client = False  # mark as unavailable, don't retry every request
    return _redis_client if _redis_client else None


# ── Embedding via fastembed (ONNX runtime — no PyTorch, ~200MB RAM) ───────────
# Uses all-MiniLM-L6-v2 via ONNX — same model used to build product embeddings
# in the DB so vectors are directly comparable. No external API calls.
_fastembed_model = None


def _get_fastembed_model():
    global _fastembed_model
    if _fastembed_model is None:
        try:
            from fastembed import TextEmbedding
            _fastembed_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
            _log.info("fastembed model loaded: all-MiniLM-L6-v2 (ONNX)")
        except Exception as e:
            _log.warning(f"fastembed unavailable, falling back to FTS only: {e}")
            _fastembed_model = False
    return _fastembed_model if _fastembed_model else None


def _embed(text: str) -> list | None:
    model = _get_fastembed_model()
    if model is None:
        return None
    try:
        return list(model.embed([text]))[0].tolist()
    except Exception as e:
        _log.warning(f"Embedding failed: {e}")
        return None

llm = __import__("langchain_groq").ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)

# ── Brand cache loaded from DB ────────────────────────────────────────────────
# Keyed by lowercase brand name, value is display name.
# Sorted longest-first so multi-word brands (e.g. "AO Smith") match before
# single-word ones (e.g. "AO").
_DB_BRANDS: dict[str, str] = {}


def _get_catalog_brands() -> dict[str, str]:
    """Return all brands from the products table, cached after first load."""
    global _DB_BRANDS
    if _DB_BRANDS:
        return _DB_BRANDS
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' AND availability = TRUE"
                )
                brands: dict[str, str] = {}
                for (brand,) in cur.fetchall():
                    b = brand.strip()
                    if b and len(b) > 1:
                        brands[b.lower()] = b
        # Sort longest first so multi-word brands match before substrings
        _DB_BRANDS = dict(sorted(brands.items(), key=lambda x: len(x[0]), reverse=True))
        _log.info(f"Loaded {len(_DB_BRANDS)} brands from DB")
    except Exception as e:
        _log.warning(f"Could not load brands from DB, falling back to BRAND_MAP: {e}")
        _DB_BRANDS = dict(BRAND_MAP)
    return _DB_BRANDS


# ── Database search (PostgreSQL full-text search) ─────────────────────────────


@tool
def search_product_catalog(
    search_query: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    sort_by: str = "relevance",
    limit: int = 5,
    retry: int = 0,
) -> str:
    """Search the product catalog using full-text search and filters.
    Returns a JSON string list of matching products with id, name, price, rating, description.
    """
    prefs = {
        "search_query": search_query,
        "category": category,
        "brand": brand,
        "max_price": max_price,
        "min_price": min_price,
        "min_rating": min_rating,
        "max_rating": max_rating,
        "sort_by": sort_by,
        "limit": limit,
    }
    results = mock_product_api_call(prefs, retry=retry)
    return _json.dumps(results, default=str)


# ToolNode for product search
product_search_tool_node = ToolNode([search_product_catalog])


def mock_product_api_call(prefs: dict, retry: int = 0) -> list:
    """Hybrid search: FTS pre-filter + pgvector semantic reranking, with Redis cache."""
    search_query = prefs.get("search_query") or ""

    # ── Redis cache lookup ────────────────────────────────────────────────────
    cache_key = "psearch:" + hashlib.md5(
        _json.dumps({**prefs, "retry": retry}, sort_keys=True).encode()
    ).hexdigest()
    redis = _get_redis()
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                _log.debug("Cache hit: %s", cache_key)
                return _json.loads(cached)
        except Exception:
            pass

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

                # Compute embedding early so we can decide whether to skip FTS WHERE filter.
                # When embedding is available we use pure semantic search (no FTS pre-filter)
                # so semantically related products (e.g. "laptop bag" for "backpack") are
                # found even when exact keywords don't match. The IVFFlat index keeps this fast.
                _query_vec = None
                if search_query and prefs.get("sort_by", "relevance") == "relevance":
                    _query_vec = _embed(search_query)

                _ACCESSORY_EXCL = (
                    "%%(charger|adapter|cable|sleeve|bag|case|stand|pouch|cover|"
                    "holder|mount|dock|hub|dongle|protector|caddy|skin|bumper|"
                    "keyboard|mouse|mice|headphone|earphone|earbud|neckband|"
                    "webcam|stylus|gamepad|controller|cooling pad|cooling table|lapdesk|"
                    "laptop table|laptop stand|desk pad|screen guard|tempered glass|"
                    "smartwatch|smart watch|fitness band|fitness tracker|"
                    "activity tracker|fitness watch|"
                    "power bank|powerbank|"
                    "remote control|remote|hdmi coupler|hdmi adapter|"
                    "fire stick|firestick|set top box|set-top box|"
                    "ink cartridge|cartridge|toner|pen drive|usb drive|"
                    "selfie stick|tripod|screen protector|tempered|"
                    "alkaline battery|alkaline|aa battery|aaa battery|"
                    "soundbar|sound bar|subwoofer|home theatre|home theater|"
                    "egg boiler|egg cooker|egg poacher|"
                    "keypad mobile|keypad phone|feature phone|bar phone|button phone)%%"
                )
                _ACCESSORY_TERMS = {
                    'charger', 'adapter', 'cable', 'sleeve', 'bag', 'case', 'stand',
                    'pouch', 'cover', 'holder', 'mount', 'dock', 'hub', 'dongle',
                    'keyboard', 'mouse', 'mice', 'headphone', 'headphones',
                    'earphone', 'earphones', 'earbud', 'earbuds',
                    'neckband', 'neckbands', 'webcam', 'stylus', 'gamepad', 'controller',
                    'watch', 'smartwatch', 'fitness', 'tracker',
                    'remote', 'remote control', 'firestick',
                    'power', 'powerbank',  # power bank
                    'boiler', 'egg boiler', 'egg cooker', 'egg poacher',  # so egg-boiler searches bypass exclusion
                }

                if search_query:
                    sq_words_norm = {w.lower().rstrip('s') for w in search_query.split()}
                    terms_norm = {t.rstrip('s') for t in _ACCESSORY_TERMS}
                    _is_accessory_search = bool(sq_words_norm & terms_norm)

                    if _query_vec:
                        # Semantic mode: skip FTS WHERE — pgvector ranks ALL products by meaning.
                        # "backpack" finds "laptop bag sleeve" even though "backpack" isn't in name.
                        # Accessory exclusion still applied as safety net for primary searches.
                        if not _is_accessory_search:
                            conditions.append(f"lower(name) NOT SIMILAR TO '{_ACCESSORY_EXCL}'")
                            # When brand is also set, add an FTS name guard to prevent off-type
                            # products from the same brand appearing (e.g. Portronics writing pads
                            # in a "Portronics speakers" search).
                            # Skip if search_query is essentially the brand name itself
                            # (e.g. LLM autocorrected "aquadpure" → search_query="aquapure",
                            # brand="Aquadpure") — the brand filter alone is sufficient.
                            _sq_norm = re.sub(r"[^a-z0-9]", "", search_query.lower())
                            _br_norm = re.sub(r"[^a-z0-9]", "", (prefs.get("brand") or "").lower())
                            _sq_is_brand = (
                                _sq_norm and _br_norm and
                                (_sq_norm in _br_norm or _br_norm in _sq_norm or
                                 _sq_norm[:6] == _br_norm[:6])
                            )
                            # Also skip FTS guard for short single-word generic queries
                            # (e.g. "phones", "laptops") — brands like Apple use "iPhone"
                            # not "phone", so plainto_tsquery('phones') won't match.
                            # The brand filter alone is sufficient for these cases.
                            _sq_is_generic = len(search_query.split()) == 1 and len(search_query) <= 10
                            if prefs.get("brand") and not _sq_is_brand and not _sq_is_generic:
                                conditions.append("search_vector @@ plainto_tsquery('english', %s)")
                                where_params.append(search_query)
                        else:
                            # Accessory search in semantic mode: also require the keyword in the
                            # product name to prevent off-category boAt/brand items (e.g. chargers)
                            # from ranking high purely due to brand similarity.
                            conditions.append("to_tsvector('english', name) @@ plainto_tsquery('english', %s)")
                            where_params.append(search_query)
                    else:
                        # FTS fallback: keyword must appear in search_vector (hard filter).
                        conditions.append("search_vector @@ plainto_tsquery('english', %s)")
                        where_params.append(search_query)
                        if not _is_accessory_search:
                            conditions.append(f"lower(name) NOT SIMILAR TO '{_ACCESSORY_EXCL}'")
                        else:
                            # For accessory-type searches in FTS mode, also require the term
                            # in the product NAME to avoid "selfie stick with carry bag" ranking
                            # above actual bags.
                            conditions.append("to_tsvector('english', name) @@ plainto_tsquery('english', %s)")
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

                if prefs.get("min_discount"):
                    conditions.append(
                        "CAST(TRIM(TRAILING '%' FROM COALESCE(discount_pct, '0')) AS INTEGER) >= %s"
                    )
                    where_params.append(int(prefs["min_discount"]))

                if prefs.get("brand"):
                    conditions.append("brand ILIKE %s")
                    where_params.append(prefs["brand"])

                where = " AND ".join(conditions)
                user_limit = prefs.get("limit") or 5
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
                elif sort_by == "discount":
                    order_clause = (
                        "CAST(TRIM(TRAILING '%' FROM COALESCE(discount_pct, '0')) AS INTEGER) DESC NULLS LAST, "
                        "rating DESC NULLS LAST"
                    )
                else:
                    if search_query:
                        if _query_vec:
                            # Semantic-primary: 30% FTS keyword signal + 70% cosine similarity.
                            # NULLS LAST prevents products with missing embeddings from floating up.
                            order_clause = (
                                "(ts_rank(search_vector, plainto_tsquery('english', %s)) * 0.3 + "
                                "(1 - (embedding <=> %s::vector)) * 0.7) DESC NULLS LAST, "
                                "rating DESC NULLS LAST"
                            )
                            order_params = [search_query, _query_vec]
                        else:
                            # FTS fallback: name-match boost + full-text rank
                            order_clause = (
                                "CASE WHEN to_tsvector('english', name) @@ plainto_tsquery('english', %s) THEN 2 "
                                "ELSE 1 END DESC, "
                                "ts_rank(search_vector, plainto_tsquery('english', %s)) DESC, "
                                "rating DESC NULLS LAST"
                            )
                            order_params = [search_query, search_query]
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
                results = [dict(r) for r in cur.fetchall()]
                if _query_vec and results:
                    _log.debug("Semantic mode — top result: %s", results[0].get("name", "")[:50])

        # ── Redis cache store ─────────────────────────────────────────────────
        if redis and results:
            try:
                redis.setex(cache_key, 300, _json.dumps(results, default=str))
            except Exception:
                pass

        return results

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

    # Deduplicate case-insensitively; ORDER BY cnt DESC means first occurrence wins
    by_cat: dict[str, dict[str, str]] = {}  # cat -> {lower_name: display_name}
    for r in rows:
        cat = r["category"] or "Other"
        brand = (r["brand"] or "").strip()
        if not brand:
            continue
        brand_lower = brand.lower()
        cat_brands = by_cat.setdefault(cat, {})
        if brand_lower not in cat_brands:
            cat_brands[brand_lower] = brand

    _ICONS = {"Electronics": "📱", "Computers&Accessories": "💻", "Home&Kitchen": "🏠"}
    lines = ["Here are all brands available in our catalog:\n"]
    for cat, brands_dict in by_cat.items():
        lines.append(f"{_ICONS.get(cat, '•')} **{cat}**")
        lines.append(", ".join(brands_dict.values()))
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

    # ── Greetings / conversational messages ──────────────
    _GOODBYE_PATTERNS = [
        r"\bbye\b", r"\bgoodbye\b", r"\bsee you\b", r"\bsee ya\b",
        r"\bcya\b", r"\bttyl\b", r"\btake care\b", r"\bgood night\b",
    ]
    if any(re.search(p, msg_lower) for p in _GOODBYE_PATTERNS):
        log.info("Goodbye detected")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": "Goodbye! Come back anytime you're looking for a product. Happy shopping!",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _THANKS_PATTERNS = [
        r"\bthank(?:s| you| u)\b", r"\bthx\b", r"\bty\b",
        r"\bcheers\b", r"\bappreciate\b",
    ]
    if any(re.search(p, msg_lower) for p in _THANKS_PATTERNS):
        log.info("Thanks detected")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": "You're welcome! Let me know if you'd like to explore more products.",
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _HOW_ARE_YOU_PATTERNS = [
        r"\bhow are you\b", r"\bhow r u\b", r"\bhow(?:'s| is) it going\b",
        r"\bhow(?:'re| are) you doing\b", r"\bhow have you been\b",
        r"\bhow do you do\b", r"\bwhat'?s up\b", r"\bwassup\b",
    ]
    if any(re.search(p, msg_lower) for p in _HOW_ARE_YOU_PATTERNS):
        log.info("How-are-you detected")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                "I'm doing great, thanks for asking! I'm here to help you find the perfect product.\n\n"
                "- **Electronics** — phones, TVs, smartwatches, earbuds, headphones, speakers, remote controls, batteries\n"
                "- **Computers & Accessories** — laptops, keyboards, mice, monitors, pen drives, USB cables, SSDs\n"
                "- **Home & Kitchen** — mixer grinders, air fryers, microwaves, fans, water purifiers, irons, kettles\n"
                "- **Office Products** — notebooks, pens, calculators, sticky notes\n\n"
                'What are you looking for? Example: *"Sony headphones under ₹5000"*'
            ),
            "total_tokens": state.get("total_tokens", 0),
            "total_cost_usd": state.get("total_cost_usd", 0.0),
        }

    _GREETING_PATTERNS = [
        r"\bhi+\b", r"\bhel+o+\b", r"\bhe+y+\b", r"\bhiya\b", r"\bhowdy\b",
        r"\byo\b", r"\bhola\b", r"\bsup\b", r"\bwassup\b", r"\bwhat'?s\s+up\b",
        r"\bnamaste\b", r"\bvanakkam\b",
        r"\bgreetings\b", r"\bgood\s+(?:morning|afternoon|evening|day)\b",
        r"\bwho are you\b", r"\bwhat are you\b",
        r"\bwhat can you do\b", r"\bwhat do you do\b",
        r"\bintroduce yourself\b",
    ]
    if any(re.search(p, msg_lower) for p in _GREETING_PATTERNS):
        log.info("Greeting detected")
        return {
            **state,
            "search_preferences": None,
            "search_retry": 0,
            "response": (
                "Hi! I'm your shopping assistant. Here's what I can help you with:\n\n"
                "- 📦 **Orders** — track deliveries, check status, view order history\n"
                "- 🛍️ **Products** — find, compare, and get recommendations from our catalog\n"
                "- 🎧 **Support** — complaints, refunds, returns, warranty claims\n\n"
                "What can I help you with today?\n"
                'Example: *"Where is my order?"*, *"Show me Sony headphones under ₹5000"*, *"I want a refund"*'
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
                "📱 **Electronics** — Smartphones, Smart TVs, Smartwatches, Earbuds, Headphones, "
                "Bluetooth Speakers, Memory Cards, Remote Controls, Batteries, Screen Guards\n"
                "💻 **Computers & Accessories** — Laptops, Monitors, Keyboards, Mice, Pen Drives, "
                "USB Cables, Hard Drives, SSDs, Laptop Bags, Printers, Webcams, USB Hubs\n"
                "🏠 **Home & Kitchen** — Mixer Grinders, Air Fryers, Microwave Ovens, Ceiling Fans, "
                "Water Purifiers, Electric Kettles, Irons, Pressure Cookers, Air Purifiers, Induction Cooktops\n"
                "📝 **Office Products** — Notebooks, Pens, Calculators, Sticky Notes, Drawing Books\n\n"
                "Popular brands: Apple, Samsung, Sony, HP, boAt, Logitech, Philips, Bajaj, Havells and more.\n\n"
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

    all_msgs = state.get("messages", [])
    # Wider window for carry-forward so brand/product survive multi-turn refinements
    # (e.g. "show headphones" → "only Sony" → "below 4000" → "above 4 stars")
    recent_msgs = all_msgs[-8:]
    conv_summary = state.get("conversation_summary") or ""

    history_lines = []
    for m in all_msgs[-2:]:  # Keep LLM prompt concise — last 2 messages only
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "").replace("\n", " ").strip()[:80]
        history_lines.append(f"{role}: {content}")
    history_snippet = "\n".join(history_lines) if history_lines else "None"

    extraction_prompt = f"""Extract product search preferences from the user message. Return ONLY JSON.

Session context (older messages, summarised):
{conv_summary if conv_summary else "None"}

Recent conversation:
{history_snippet}

User: "{msg}"

JSON format:
{{"search_query":null,"brand":null,"category":null,"max_price":null,"min_price":null,"min_rating":null,"max_rating":null,"min_discount":null,"sort_by":"relevance","limit":5}}

Rules:
- search_query: the product the user wants as a short descriptive phrase.
  Keep meaningful attributes: "wireless mouse", "noise cancelling headphone", "gaming laptop", "mixer grinder".
  Context mappings: "for commute/gym/workout/running" → "earbuds", "for studying/office/calls" → "headphone",
  "for coffee" → "coffee maker", "for cooking/kitchen" → "mixer grinder", "for home office" → "monitor".
  Product name mappings: "remote control/TV remote/universal remote/DTH remote" → search_query="remote control" brand=null,
  "set top box/set-top box/DTH box" → search_query="set top box" brand=null.
  Set null ONLY if no product is implied (pure price/rating filter with zero product context).
- brand: only if the user explicitly names a real manufacturer brand (Samsung, Sony, Logitech, boAt, LG, HP, etc.).
  Never treat product-type words as brands: "remote", "universal", "compatible", "replacement", "cable", "cover" are NOT brands — set brand=null for these.
  CRITICAL: "noise cancelling" / "noise reduction" / "noise isolating" / "noise blocking" — "noise" here is an ADJECTIVE, NOT the brand "Noise". Set brand=null for these phrases.
  Special brand mappings: "amazon basics" / "amazon basic" / "amazonbasics" → brand="AmazonBasics", "amazon brand" / "solimo" → brand="Amazon", "ao smith" → brand="AO Smith".
- category:
  "Electronics" → smartphones/mobile phones, smart TVs, smartwatches/fitness bands, TWS earbuds/wireless earbuds, wired earphones/earphones, headphones (on-ear/over-ear/neckband), Bluetooth speakers/portable speakers, memory cards/microSD cards, screen guards/tempered glass/screen protectors, batteries (alkaline/rechargeable), TV remote controls/universal remotes/DTH remotes, set-top boxes/DTH boxes.
  "Computers&Accessories" → laptops/MacBooks/notebooks (computing), monitors/displays, keyboards (wired/wireless/gaming), mice (wired/wireless/gaming), USB cables (type-C/lightning/micro-USB/braided), pen drives/USB flash drives/USB sticks, external hard drives/SSDs/portable storage, laptop bags/sleeves/cases/backpacks, USB hubs/adapters, screen protectors (laptop/tablet), LCD writing tablets/drawing tablets, printers, 4G data cards/WiFi hotspot dongles, webcams, cooling pads, cable organisers.
  "Home&Kitchen" → microwave ovens/solo microwave/grill microwave/convection microwave, mixer grinders/blenders/juicers/hand blenders, air fryers, electric kettles, pressure cookers, water purifiers/RO/water filters, ceiling fans/table fans/pedestal fans, irons/dry irons/steam irons/garment steamers, air purifiers, induction cooktops, OTG ovens, instant pots/multi-cookers, laundry baskets/laundry bags, kitchen weighing scales, washing machines (if any).
  "OfficeProducts" → notebooks/writing books/diaries/notepads, ballpoint pens/fountain pens/gel pens/markers, scientific calculators/basic calculators, sticky notes/post-it notes, drawing books/sketchbooks.
  null if the query spans multiple categories or is genuinely unclear.
- max_price: numeric for "under/below/within/less than ₹X". Also set for the upper bound of "between X and Y".
- min_price: numeric for "above/over/more than ₹X". Also set for the lower bound of "between X and Y".
- min_rating: numeric for "rated above X" or "X stars and above".
- max_rating: numeric for "rated below X".
- min_discount: numeric (0-100) for "X% off", "above X% discount", "at least X% off".
- sort_by: "price_asc" if cheapest/budget/lowest price/most affordable, "price_desc" if most expensive/premium,
  "rating" if best rated/top rated, "new" if new arrivals/latest/newest/just launched/recently added,
  "discount" if maximum discount/most discounted/highest discount/best deal/best offer/on sale,
  "relevance" (default for everything else).
- limit: number if user says "top N" or "best N". "all/show all" → 10. Default 5.
- FOLLOW-UP: if the message is a short refinement ("only boAt", "under 2000", "show cheaper", "only amazon basics"),
  carry the product type AND category EXACTLY from the most recent product search in conversation history.
  Do NOT infer or guess a new product type from the brand name — always use the PREVIOUS search_query unchanged.
  Example: history="toasters" + "only Philips" → search_query="toasters", brand="Philips" (NOT "light bulb" or any other product).
  Example: history="smartwatches" + "only Apple" → search_query="smartwatches", brand="Apple", category="Electronics".
  Example: history="kettle" (Home&Kitchen) + "only amazon basics" → search_query="kettle", brand="AmazonBasics", category="Home&Kitchen".
  Example: history="laptops" (Computers&Accessories) + "only HP under 60000" → search_query="laptops", brand="HP", max_price=60000, category="Computers&Accessories".

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
            "min_discount": None,
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
        "min_discount": extracted.get("min_discount"),
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
        # Pattern A: "X stars/rating and below" — negative lookahead ensures "below" isn't
        # followed by a digit (which would mean it's a price threshold, e.g. "4.2 ratings and below 1000")
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:star|rating)s?\s*(?:and\s+)?(?:below|under)(?!\s*\d)",
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

    # "between X and Y" / "from X to Y" price range
    if not prefs.get("min_price") or not prefs.get("max_price"):
        m = re.search(
            r"(?:between|from)\s+(?:rs\.?|₹)?(\d+(?:,\d+)*)\s+(?:and|to)\s+(?:rs\.?|₹)?(\d+(?:,\d+)*)",
            msg_lower,
        )
        if m:
            lo, hi = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            if lo < hi:
                if not prefs.get("min_price"):
                    prefs["min_price"] = lo
                if not prefs.get("max_price"):
                    prefs["max_price"] = hi

    # Discount filter: "50% off", "above 40% discount", "minimum 30% off"
    if not prefs.get("min_discount"):
        m = re.search(
            r"(?:above|over|minimum|at least|more than\s+)?(\d+)\s*%\s*(?:off|discount|sale)",
            msg_lower,
        )
        if m:
            prefs["min_discount"] = int(m.group(1))

    # Discount sort: "maximum discount", "most discounted", "highest discount", "best deal/offer"
    if prefs.get("sort_by", "relevance") == "relevance":
        if re.search(
            r"\b(?:max(?:imum)?\s+discount|most\s+discounted|highest\s+discount|"
            r"best\s+(?:deal|offer|price\s+drop)|biggest\s+discount|on\s+sale)\b",
            msg_lower,
        ):
            prefs["sort_by"] = "discount"

    # Sanity-check: if LLM set min_price/max_price or min_rating/max_rating to the same
    # value (e.g. LLM misread "below 1000" as min_price=1000 and regex also set max_price=1000),
    # the impossible constraint returns zero results — clear the one that is wrong.
    if prefs.get("min_price") and prefs.get("max_price") and prefs["min_price"] >= prefs["max_price"]:
        prefs["min_price"] = None
    if prefs.get("min_rating") and prefs.get("max_rating") and prefs["min_rating"] >= prefs["max_rating"]:
        prefs["max_rating"] = None

    if re.search(r"\b(all|every|complete list)\b", msg_lower):
        prefs["limit"] = max(prefs.get("limit") or 5, 10)

    # Context-bias correction: if the current message explicitly mentions a product type
    # but the LLM was biased by session history and set a different search_query, fix it.
    _MSG_PRODUCT_OVERRIDES = [
        (r"\bsmart\s*phone|\bsmartphone", "smartphone"),
        (r"\blaptop|\bnotebook", "laptop"),
        (r"\bearphone|\bearbud|\bheadphone|\bneckband", "earphone"),
        (r"\bspeaker\b", "speaker"),
        (r"\btablet\b", "tablet"),
        (r"\bwatch|\bsmartwatch", "smartwatch"),
        (r"\bpurifier\b|\bro\s+water", "water purifier"),
        (r"\bcooker\b", "pressure cooker"),
        (r"\bkettle\b", "electric kettle"),
        (r"\bmixer\b|\bgrinder\b", "mixer grinder"),
        (r"\bfan\b", "fan"),
        (r"\biron\b", "iron"),
    ]
    for _pat, _override in _MSG_PRODUCT_OVERRIDES:
        if re.search(_pat, msg_lower):
            sq = (prefs.get("search_query") or "").lower()
            # Only override if the current search_query doesn't already reflect the intent
            if sq and not any(w in sq for w in _override.split()):
                prefs["search_query"] = _override
            break

    # If "noise" appears as adjective (noise cancelling/reduction), clear any brand="Noise" the LLM set
    if (prefs.get("brand") or "").lower() == "noise" and re.search(
        r"\bnoise\s+(?:cancell|reduc|isolat|block)", msg_lower
    ):
        prefs["brand"] = None

    # Multi-word / variant aliases that DB token scan can't handle (checked first).
    _BRAND_ALIASES = [
        (r"\bamazon\s+basics?\b", "AmazonBasics"),
        (r"\bamazonbasics\b",     "AmazonBasics"),
        (r"\bao\s+smith\b",       "AO Smith"),
        (r"\btp[\s-]link\b",      "TP-Link"),
        # Typo variants
        (r"\bxioami\b",           "Xiaomi"),
        (r"\bxaomi\b",            "Xiaomi"),
        (r"\bsamsumg\b",          "Samsung"),
        (r"\bphlips\b",           "Philips"),
    ]
    if not prefs.get("brand"):
        for pattern, canonical in _BRAND_ALIASES:
            if re.search(pattern, msg_lower):
                prefs["brand"] = canonical
                break

    # Brand fallback: scan message for known brands.
    # Prefer the brand that appears EARLIEST in the message so "apple iphone" picks
    # "Apple" (pos 5) over "iPhone" (pos 11, but that's an accessory brand in the DB).
    # Resolve ties (same start position) by taking the LONGEST match so "AO Smith"
    # wins over "AO".
    if not prefs.get("brand"):
        best_brand: str | None = None
        best_pos = len(msg_lower) + 1
        best_len = 0
        for token, display in _get_catalog_brands().items():
            m_b = re.search(rf"\b{re.escape(token)}\b", msg_lower)
            if m_b:
                pos = m_b.start()
                if pos < best_pos or (pos == best_pos and len(token) > best_len):
                    best_pos, best_len, best_brand = pos, len(token), display
        if best_brand:
            prefs["brand"] = best_brand

    # Clean search_query of brand name and generic browse words.
    # e.g. "tata products" + brand="Tata"  → None   (nothing meaningful left)
    # e.g. "dell laptop"   + brand="Dell"  → "laptop" (strip brand prefix)
    # e.g. "WeRun"         + brand="10WeRun" → None  (sq is partial brand name)
    if prefs.get("brand") and prefs.get("search_query"):
        sq_lower = prefs["search_query"].lower()
        brand_lower = prefs["brand"].lower()
        _BROWSE_NOISE = {
            "products", "product", "items", "item", "show", "me", "all", "best", "good", "top",
            # prepositions/articles that LLMs sometimes leave in extracted queries
            "for", "by", "from", "of", "in", "with", "to", "at", "a", "an", "the", "and", "or",
        }
        sq_meaningful_words = [w for w in sq_lower.split() if w not in _BROWSE_NOISE and w != brand_lower]
        sq_meaningful = " ".join(sq_meaningful_words)
        # Also clear when sq is a typo/autocorrect of the brand (common 6-char prefix match)
        _sq_norm2 = re.sub(r"[^a-z0-9]", "", sq_meaningful)
        _br_norm2 = re.sub(r"[^a-z0-9]", "", brand_lower)
        _is_brand_typo = (
            _sq_norm2 and _br_norm2 and len(_sq_norm2) >= 4 and
            (_sq_norm2 in _br_norm2 or _br_norm2 in _sq_norm2 or
             (_sq_norm2[:6] == _br_norm2[:6] if len(_sq_norm2) >= 6 and len(_br_norm2) >= 6 else False))
        )
        if not sq_meaningful or sq_meaningful in brand_lower or _is_brand_typo:
            prefs["search_query"] = None
        elif sq_meaningful != sq_lower:
            prefs["search_query"] = sq_meaningful  # strip brand prefix (e.g. "dell laptop" → "laptop")

    # ── Carry-forward from conversation history ───────────
    # Fires when the current message looks like a refinement of the previous search.
    # Two trigger conditions:
    #   1. Has a price/rating filter but no product type (e.g. "above 40000")
    #   2. Is a short modifier message ≤4 words (e.g. "only hp", "just Samsung")
    _has_filter = prefs.get("max_price") or prefs.get("min_price") or prefs.get("min_rating") or prefs.get("max_rating")
    _is_refinement = _has_filter or len(msg.strip().split()) <= 4

    # For short refinements with NO search_query, don't trust the LLM's category.
    # But preserve category when user explicitly named a product type
    # (e.g. "show smartphones" keeps Electronics so USB drives are excluded).
    if _is_refinement and not prefs.get("search_query"):
        prefs["category"] = None

    if _is_refinement and recent_msgs:
        user_msgs = [m for m in recent_msgs if m.get("role") == "user"]

        # Brand carryforward: check USER messages only to avoid false matches
        # from product descriptions in assistant responses.
        # Context check: verify current product type appears ANYWHERE in recent user
        # messages (not just the message containing the brand) so multi-step chains
        # like "show laptops → only dell → below 90000" keep Dell at turn 3.
        if not prefs.get("brand"):
            sq = prefs.get("search_query") or ""
            sq_words = [w for w in sq.split() if len(w) > 2]
            # Context check: look in ALL recent messages (user + assistant) so that
            # "show headphones → only Sony → below 20000" still carries Sony at turn 3.
            # Without this, "headphones" from carry-forward never appears in user msgs
            # alone, so overall_context_ok = False and Sony is dropped.
            all_recent_content = " ".join(
                (m.get("content") or "").lower()
                for m in recent_msgs
                if (m.get("content") or "").lower().strip() != msg_lower.strip()
            )
            overall_context_ok = not sq_words or any(
                re.search(rf"\b{re.escape(w)}\b", all_recent_content) for w in sq_words
            )
            if overall_context_ok:
                for hist_m in reversed(user_msgs):
                    hist_content = (hist_m.get("content") or "").lower()
                    for token, display in _get_catalog_brands().items():
                        if re.search(rf"\b{re.escape(token)}\b", hist_content):
                            prefs["brand"] = display
                            log.info(f"Carried forward brand: {display}")
                            break
                    if prefs.get("brand"):
                        break

        # search_query carryforward: skip when user is asking to browse a brand's full
        # catalog (e.g. "show JIALTO products", "show HP products") — carrying forward
        # a product type from history would incorrectly filter to that type only.
        _brand_browse = bool(prefs.get("brand")) and re.search(
            r"\bproducts?\b|\bshow\b|\bbrowse\b|\ball\b", msg_lower
        )
        if not prefs.get("search_query") and not _brand_browse:
            # Primary (dynamic): extract what the previous response was actually about
            # from the "Here are the top **X** recommendations" header — works for any
            # product in the DB without a hardcoded list.
            catalog_brands_lower = set(_get_catalog_brands().keys())
            # Search recent messages first, then fall back to conversation summary
            # (summary covers older turns pushed out of the sliding window — this is
            # what breaks "show HP mouse" → "only hp" after several more exchanges).
            _header_sources = (
                [(hist_m.get("content") or "") for hist_m in reversed(recent_msgs)
                 if hist_m.get("role") == "assistant"]
                + ([conv_summary] if conv_summary else [])
            )
            for content in _header_sources:
                m_sq = re.search(r"Here are (?:the )?top \*\*(.+?)\*\* recommendations", content)
                if m_sq:
                    sq_candidate = m_sq.group(1).strip()
                    sq_cand_lower = sq_candidate.lower()
                    # Skip brand-only headers (e.g. "Dell products") and generic words
                    if (sq_cand_lower not in _GENERIC_WORDS
                            and sq_cand_lower not in catalog_brands_lower
                            and not sq_cand_lower.endswith(" products")):
                        prefs["search_query"] = sq_candidate
                        log.info(f"Carried forward search_query from response: {sq_candidate}")
                        break

            # Fallback: scan history + summary for known product types
            if not prefs.get("search_query"):
                _text_sources = (
                    [(hist_m.get("content") or "").lower() for hist_m in reversed(recent_msgs)]
                    + ([conv_summary.lower()] if conv_summary else [])
                )
                for hist_content in _text_sources:
                    for pt in _CARRY_PRODUCT_TYPES:
                        if re.search(rf"\b{re.escape(pt)}\b", hist_content):
                            prefs["search_query"] = pt
                            log.info(f"Carried forward search_query: {pt}")
                            break
                    if prefs.get("search_query"):
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
    """Calls search_product_catalog via ToolNode and stores results in state."""
    log = get_log(state["request_id"], "product_agent", "search_products")
    log.info("Tool called: search_products via ToolNode")

    prefs = state.get("search_preferences", {})
    retry = state.get("search_retry", 0)

    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_product_catalog",
                "args": {
                    "search_query": prefs.get("search_query"),
                    "category": prefs.get("category"),
                    "brand": prefs.get("brand"),
                    "max_price": prefs.get("max_price"),
                    "min_price": prefs.get("min_price"),
                    "min_rating": prefs.get("min_rating"),
                    "max_rating": prefs.get("max_rating"),
                    "sort_by": prefs.get("sort_by", "relevance"),
                    "limit": prefs.get("limit", 5),
                    "retry": retry,
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )
    tool_result = product_search_tool_node.invoke({"messages": [ai_msg]})
    results = _json.loads(tool_result["messages"][-1].content)

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
    dropped_brand = state.get("dropped_brand")

    if retry == 0:
        dropped_brand = prefs.get("brand") or dropped_brand
        if not prefs.get("search_query"):
            # Brand-only browse with no results — skip broadening to avoid returning
            # random top-rated products; jump straight to no_results_response.
            return {**state, "search_preferences": prefs, "search_retry": 2, "dropped_brand": dropped_brand}
        prefs = {**prefs, "brand": None}
    elif retry == 1:
        sq = prefs.get("search_query") or ""
        if sq:
            words = sq.split()
            simplified = words[-1] if words else sq
            # Don't simplify to generic words — FTS("products") matches everything
            prefs = {**prefs, "search_query": simplified if simplified.lower() not in _GENERIC_WORDS else None}
        if prefs.get("max_price"):
            prefs = {**prefs, "max_price": prefs["max_price"] * 1.5}
        prefs = {**prefs, "category": None}

    log.info(f"Broadening search (retry {retry + 1}): {prefs}")
    return {**state, "search_preferences": prefs, "search_retry": retry + 1, "dropped_brand": dropped_brand,
            "search_broadened": True}


def no_results_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "no_results_response")
    log.warning("No products found after retries")

    sq = (state.get("search_preferences") or {}).get("search_query") or ""

    # dropped_brand is set by broaden_search when it strips the brand filter.
    # Fall back to scanning the original message using live DB brands (not the
    # static BRAND_MAP which misses dynamic brands like "10WeRun", "Camel", etc.)
    original_brand = state.get("dropped_brand")
    if not original_brand:
        msg_lower = state["current_input"].lower()
        for token, display in _get_catalog_brands().items():
            if re.search(rf"\b{re.escape(token)}\b", msg_lower):
                original_brand = display
                break

    if original_brand and sq:
        response = (
            f"**{original_brand}** doesn't carry **{sq}** in our catalog.\n\n"
            f'Try *"show me {sq}"* to see options from all brands, '
            f'or *"show me {original_brand} products"* to browse what {original_brand} offers.'
        )
    elif original_brand:
        response = (
            f"I couldn't find any products from **{original_brand}** in our catalog.\n\n"
            f'Try a different brand or search for a specific product type.'
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

    # Build effective user request that includes search context so the ranking LLM
    # knows the INTENT, not just the raw follow-up ("only apple" → "Apple laptop").
    search_prefs = state.get("search_preferences") or {}
    _sq = search_prefs.get("search_query") or ""
    _br = search_prefs.get("brand") or ""
    if _sq and _br:
        effective_request = f"{_br} {_sq}"
    elif _sq:
        effective_request = _sq
    elif _br:
        effective_request = f"{_br} products"
    else:
        effective_request = state["current_input"]

    prompt_template = mlflow.genai.load_prompt("prompts:/product_ranking_prompt/1")
    prompt = prompt_template.format(
        user_request=effective_request,
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


@tool
def get_product_reviews(product_ids: List[str]) -> str:
    """Fetch top-3 reviews per product from the reviews table.
    Returns JSON: {product_id: [{review_title, review_text, rating}, ...]}
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT product_id, review_title, review_text, rating "
                    "FROM reviews WHERE product_id = ANY(%s) ORDER BY rating DESC",
                    [product_ids],
                )
                reviews_by_id: dict = {}
                for row in cur.fetchall():
                    pid = row["product_id"]
                    if pid not in reviews_by_id:
                        reviews_by_id[pid] = []
                    if len(reviews_by_id[pid]) < 3:
                        reviews_by_id[pid].append(dict(row))
        return _json.dumps(reviews_by_id, default=str)
    except Exception:
        return _json.dumps({})


@tool
def get_product_specs(product_ids: List[str]) -> str:
    """Fetch extended specs (description, rating_count, discount, original_price) per product.
    Returns JSON: {product_id: {description, rating, rating_count, discount_pct, original_price}}
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT product_id, description, rating, rating_count, discount_pct, original_price "
                    "FROM products WHERE product_id = ANY(%s)",
                    [product_ids],
                )
                return _json.dumps({row["product_id"]: dict(row) for row in cur.fetchall()}, default=str)
    except Exception:
        return _json.dumps({})


# ToolNode for product enrichment (reviews + specs)
product_enrichment_tool_node = ToolNode([get_product_reviews, get_product_specs])


def fetch_reviews(state: AgentState) -> AgentState:
    """Fetches product reviews via ToolNode and enriches ranked_products."""
    log = get_log(state["request_id"], "product_agent", "fetch_reviews")
    products = state.get("ranked_products", [])
    product_ids = [p["product_id"] for p in products]

    if not product_ids:
        return {**state, "enriched_products": products}

    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_product_reviews", "args": {"product_ids": product_ids}, "id": call_id, "type": "tool_call"}],
    )
    result = product_enrichment_tool_node.invoke({"messages": [ai_msg]})
    reviews_by_id = _json.loads(result["messages"][-1].content)

    enriched = [{**p, "reviews": reviews_by_id.get(p["product_id"], [])} for p in products]
    log_tool_span(
        span_name="fetch_reviews", tool_name="reviews_table",
        tool_input={"product_count": len(products)}, tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )
    log.info(f"Fetched reviews for {len(enriched)} products")
    return {**state, "enriched_products": enriched}


def fetch_specs(state: AgentState) -> AgentState:
    """Fetches product specs via ToolNode and enriches enriched_products."""
    log = get_log(state["request_id"], "product_agent", "fetch_specs")
    products = state.get("enriched_products", [])
    product_ids = [p["product_id"] for p in products]

    if not product_ids:
        return {**state, "enriched_products": products}

    call_id = str(uuid.uuid4())[:8]
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_product_specs", "args": {"product_ids": product_ids}, "id": call_id, "type": "tool_call"}],
    )
    result = product_enrichment_tool_node.invoke({"messages": [ai_msg]})
    specs_by_id = _json.loads(result["messages"][-1].content)

    enriched = [{**p, "specs": specs_by_id.get(p["product_id"], {})} for p in products]
    log_tool_span(
        span_name="fetch_specs", tool_name="products_specs",
        tool_input={"product_count": len(products)}, tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
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

    # Do NOT sort by score — semantic ranking from the DB query is the authority.
    # Sorting here by reviews/discount overrides semantic relevance (e.g. a TV remote
    # with reviews beats a headphone without reviews for a "headphones" search).
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

    _brand = search_prefs.get("brand")
    search_query = search_prefs.get("search_query") or (
        f"{_brand} products" if _brand else "product"
    )
    dropped_brand = state.get("dropped_brand")
    search_broadened = state.get("search_broadened", False)
    if dropped_brand:
        lines = [
            f"**{dropped_brand}** doesn't carry **{search_query}** in our catalog.\n\n"
            f"Here are the best alternatives from other brands:\n"
        ]
    elif search_broadened:
        lines = [
            f"I couldn't find an exact match for **{search_query}**, "
            f"but here are the closest options available:\n"
        ]
    else:
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
    graph.add_node("search_products", search_products)          # calls product_search_tool_node internally
    graph.add_node("product_search_tools", product_search_tool_node)       # ToolNode — search_product_catalog
    graph.add_node("product_enrichment_tools", product_enrichment_tool_node)  # ToolNode — reviews + specs
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
