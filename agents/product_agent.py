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

_log = logging.getLogger(__name__)

llm = __import__("langchain_groq").ChatGroq(
    model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY
)

# ── Module-level constants ─────────────────────────────────────────────────────

_CATEGORY_NORM = {
    "electronics":              "Electronics",
    "computers&accessories":    "Computers&Accessories",
    "computers & accessories":  "Computers&Accessories",
    "computers and accessories":"Computers&Accessories",
    "computers":                "Computers&Accessories",
    "home&kitchen":             "Home&Kitchen",
    "home & kitchen":           "Home&Kitchen",
    "home and kitchen":         "Home&Kitchen",
    "kitchen":                  "Home&Kitchen",
    "home":                     "Home&Kitchen",
}

BRAND_MAP = {
    "hp": "HP", "dell": "Dell", "apple": "Apple", "samsung": "Samsung",
    "sony": "Sony", "lenovo": "Lenovo", "oneplus": "OnePlus", "boat": "boAt",
    "asus": "ASUS", "acer": "Acer", "mi": "Mi", "realme": "Realme",
    "redmi": "Redmi", "motorola": "Motorola", "nokia": "Nokia",
    "oppo": "OPPO", "vivo": "Vivo", "google": "Google", "lg": "LG",
    "panasonic": "Panasonic", "philips": "Philips", "bajaj": "Bajaj",
    "prestige": "Prestige", "daikin": "Daikin", "voltas": "Voltas",
    "whirlpool": "Whirlpool", "bosch": "Bosch", "kent": "Kent",
    "aquaguard": "Aquaguard", "havells": "Havells", "instant": "Instant",
    "tefal": "Tefal", "milton": "Milton", "pigeon": "Pigeon",
    "hawkins": "Hawkins", "cello": "Cello", "borosil": "Borosil",
    "butterfly": "Butterfly", "vinod": "Vinod", "ifb": "IFB",
    "tcl": "TCL", "hisense": "Hisense",
}

_GENERIC_WORDS = {
    "product", "products", "item", "items", "thing", "things",
    "anything", "something", "goods", "appliance", "appliances",
}

_CARRY_PRODUCT_TYPES = [
    "laptop", "phone", "smartphone", "tablet", "tv", "television",
    "camera", "watch", "smartwatch", "desktop", "computer",
    "earphone", "headphone", "earbuds", "earbud", "speaker",
    "neckband", "headset", "keyboard", "mouse", "monitor", "charger",
    "mixer grinder", "air conditioner", "washing machine", "water purifier",
    "microwave", "air fryer", "electric kettle", "rice cooker",
    "refrigerator", "pressure cooker", "water bottle",
]

# Keyword → SQL ILIKE pattern expansions
_PHONE_SQL_PATTERNS = [
    "%galaxy%", "%iphone%", "%5g%", "%pixel%", "%nord%",
    "%redmi%", "%realme%", "%narzo%", "%moto%", "%oneplus%",
    "%xperia%", "%nothing phone%",
]
_KITCHEN_SQL_PATTERNS = [
    "%mixer grinder%", "%electric kettle%", "%air fryer%",
    "%pressure cooker%", "%microwave%", "%induction cooktop%",
    "%induction stove%", "%rice cooker%", "%blender%",
    "%juicer%", "%toaster%", "%coffee maker%",
    "%coffee machine%", "%sandwich maker%",
    "%water bottle%", "%flask%",
]
_HOME_APPLIANCE_SQL_PATTERNS = [
    "%refrigerator%", "%fridge%", "%washing machine%",
    "%air conditioner%", "%water purifier%",
    "%microwave%", "%geyser%", "%water heater%",
    "%television%", "%smart tv%",
]
_ENERGY_SQL_PATTERNS = [
    "%inverter%", "%5 star%", "%5-star%",
    "%energy efficient%", "%energy saver%", "%energy saving%",
]
_SMARTWATCH_SQL_PATTERNS = ["%watch%", "%smartwatch%"]
_TABLET_SQL_PATTERNS    = ["%ipad%", "%galaxy tab%"]
_EARBUDS_SQL_PATTERNS   = ["%earbuds%", "%airpods%", "%airdopes%"]
_TV_SQL_PATTERNS        = ["%smart tv%", "%television%", "% tv %", "% tv"]

_PHONE_KEYWORDS         = {"phone", "smartphone", "mobile"}
_KITCHEN_KEYWORDS       = {
    "kitchen appliance", "kitchen appliances", "cooking appliance",
    "cooking appliances", "kitchen", "cooking", "kitchen items",
    "kitchen products", "kitchen tools", "kitchen gadget", "kitchen gadgets",
    "kitchen gift", "gift for kitchen",
}
_HOME_APPLIANCE_KEYWORDS = {"home appliance", "home appliances", "home essential", "home essentials"}
_ENERGY_KEYWORDS         = {
    "energy saving", "energy efficient", "power saving",
    "energy saving appliance", "energy saving appliances",
    "energy-saving", "eco-friendly", "eco friendly",
}
_SMARTWATCH_KEYWORDS = {"smartwatch", "smartwatches", "watch", "watches", "smart watch"}
_TABLET_KEYWORDS     = {"tablet", "tablets", "ipad"}
_EARBUDS_KEYWORDS    = {"earbud", "earbuds", "airpods", "air pods"}
_TV_KEYWORDS         = {"tv", "television", "smart tv", "oled tv", "qled tv", "4k tv"}

_KEYWORD_TO_SQL_PATTERNS = [
    (_PHONE_KEYWORDS,          _PHONE_SQL_PATTERNS),
    (_KITCHEN_KEYWORDS,        _KITCHEN_SQL_PATTERNS),
    (_HOME_APPLIANCE_KEYWORDS, _HOME_APPLIANCE_SQL_PATTERNS),
    (_ENERGY_KEYWORDS,         _ENERGY_SQL_PATTERNS),
    (_SMARTWATCH_KEYWORDS,     _SMARTWATCH_SQL_PATTERNS),
    (_TABLET_KEYWORDS,         _TABLET_SQL_PATTERNS),
    (_EARBUDS_KEYWORDS,        _EARBUDS_SQL_PATTERNS),
    (_TV_KEYWORDS,             _TV_SQL_PATTERNS),
]

_MAIN_PRODUCT_TYPES = [
    "laptop", "phone", "smartphone", "tablet", "tv", "television",
    "camera", "watch", "smartwatch", "desktop", "computer",
    "earphone", "headphone", "earbuds", "earbud", "speaker",
    "neckband", "headset",
    "mixer grinder", "air conditioner", "washing machine",
    "water purifier", "microwave oven", "air fryer",
    "induction cooktop", "electric kettle", "rice cooker",
    "refrigerator", "pressure cooker", "water bottle",
    "coffee maker", "blender", "juicer", "toaster",
    "kitchen appliance", "home appliance", "energy saving",
]

_ACCESSORY_KEYWORDS = [
    "mouse", "cable", "adapter", "charger", "stand",
    "bag", "case", "cover", "keyboard", "hub",
    "dongle", "wire", "cord", "sleeve", "memory",
    "mousepad", "mat", "cooling pad", "protector",
    "organizer", "pouch", "winder", "remote",
    "wall mount", "bracket", "antenna",
    "cleaning kit", "cleaning cloth", "microfiber",
    "screen cleaner", "cleaning spray", "dust blower",
    "compressed air", "lens cleaner", "wipe",
]

_PHONE_EXTRA_EXCLUSIONS  = ["earphone", "earphones", "headset", "handsfree",
                             "neckband", "earbuds", "watch", "smartwatch",
                             "tablet", "tab", "buds"]
_LAPTOP_EXTRA_EXCLUSIONS = ["headphone", "earphone", "speaker", "webcam",
                             "headset", "earbuds", "neckband"]

_CHARGER_EXCLUSIONS = [
    "watch charger", "smartwatch charger", "smart watch charger",
    "cable protector", "cord protector", "charger protector",
    "charging stand", "charger included", "charger in box", "with charger",
]

_BROAD_INTENTS = {"kitchen appliance", "home appliance", "energy saving"}

_TYPE_SIGNATURES = [
    ("mixer",        "mixer grinder"),
    ("kettle",       "electric kettle"),
    ("fryer",        "air fryer"),
    ("cooker",       "pressure cooker"),
    ("microwave",    "microwave"),
    ("induction",    "induction cooktop"),
    ("rice",         "rice cooker"),
    ("coffee",       "coffee maker"),
    ("blender",      "blender"),
    ("juicer",       "juicer"),
    ("toaster",      "toaster"),
    ("sandwich",     "sandwich maker"),
    ("refrigerator", "refrigerator"),
    ("fridge",       "refrigerator"),
    ("washing",      "washing machine"),
    ("conditioner",  "air conditioner"),
    ("purifier",     "water purifier"),
    ("television",   "television"),
    ("inverter",     "inverter appliance"),
]


# ── Database search ────────────────────────────────────────────────────────────

def mock_product_api_call(prefs: dict, retry: int = 0) -> list:
    """Simulates an external product catalog API. Replace with real HTTP call in production."""
    max_price = prefs.get("max_price")

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                conditions = ["availability = TRUE"]
                params     = []

                if prefs.get("category"):
                    conditions.append("category ILIKE %s")
                    params.append(f"%{prefs['category']}%")

                if max_price:
                    conditions.append("price <= %s")
                    params.append(max_price)

                if prefs.get("min_price"):
                    conditions.append("price >= %s")
                    params.append(prefs["min_price"])

                if prefs.get("min_rating"):
                    conditions.append("rating >= %s")
                    params.append(prefs["min_rating"])

                if prefs.get("max_rating"):
                    conditions.append("rating < %s")
                    params.append(prefs["max_rating"])

                if prefs.get("brand"):
                    conditions.append("brand ILIKE %s")
                    params.append(f"%{prefs['brand']}%")

                if prefs.get("keywords"):
                    all_name_patterns = []
                    for k in prefs["keywords"]:
                        kl = k.lower()
                        matched = False
                        for keyword_set, patterns in _KEYWORD_TO_SQL_PATTERNS:
                            if kl in keyword_set:
                                all_name_patterns.extend(patterns)
                                matched = True
                                break
                        if not matched:
                            all_name_patterns.append(f"%{k}%")

                    keyword_conditions = " OR ".join(["name ILIKE %s"] * len(all_name_patterns))
                    conditions.append(f"({keyword_conditions})")
                    params.extend(all_name_patterns)

                where       = " AND ".join(conditions)
                user_limit  = prefs.get("limit", 5)
                fetch_limit = max(user_limit * 5, 20)
                query       = f"SELECT * FROM products WHERE {where} ORDER BY rating DESC NULLS LAST LIMIT {fetch_limit}"
                _log.debug("Product search SQL: %s | params: %s", query, params)
                cur.execute(query, params)
                results = [dict(r) for r in cur.fetchall()]

                # Filter out accessories when searching for a specific product type
                searched_type = None
                keywords_str  = " ".join(prefs.get("keywords", []))
                for pt in _MAIN_PRODUCT_TYPES:
                    if pt in keywords_str.lower():
                        searched_type = pt
                        break

                exclusions = list(_ACCESSORY_KEYWORDS)
                if searched_type in ("phone", "smartphone"):
                    exclusions = exclusions + _PHONE_EXTRA_EXCLUSIONS
                elif searched_type == "laptop":
                    exclusions = exclusions + _LAPTOP_EXTRA_EXCLUSIONS

                if searched_type:
                    filtered = [r for r in results if not any(
                        re.search(rf'\b{re.escape(acc)}(?:e?s)?(?:[^a-zA-Z]|$)', r["name"].lower())
                        for acc in exclusions
                    )]
                    if filtered:
                        results = filtered

                # Exclude irrelevant charger products
                kw_joined = " ".join(prefs.get("keywords", [])).lower()
                if "charger" in kw_joined:
                    no_irrelevant = [
                        r for r in results
                        if not any(kw in r["name"].lower() for kw in _CHARGER_EXCLUSIONS)
                    ]
                    if no_irrelevant:
                        results = no_irrelevant

                # Diversity filter for broad category queries
                keywords_lower = " ".join(prefs.get("keywords", [])).lower()
                if any(intent in keywords_lower for intent in _BROAD_INTENTS):
                    seen_types = set()
                    diverse    = []
                    for r in results:
                        name_lower = r["name"].lower()
                        assigned   = None
                        for sig, tp in _TYPE_SIGNATURES:
                            if sig in name_lower:
                                assigned = tp
                                break
                        key = assigned or name_lower[:20]
                        if key not in seen_types:
                            diverse.append(r)
                            seen_types.add(key)
                    if diverse:
                        results = diverse

        return results

    except Exception as e:
        _log.error("Product DB query failed: %s", e)
        return []


# ── Agent nodes ────────────────────────────────────────────────────────────────

def extract_preferences(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "extract_preferences")
    log.info("Node entered")

    msg = state["current_input"]

    recent_msgs    = state.get("messages", [])[-2:]
    history_lines  = []
    for m in recent_msgs:
        role    = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "").replace("\n", " ").strip()[:80]
        history_lines.append(f"{role}: {content}")
    history_snippet = "\n".join(history_lines) if history_lines else "None"

    extraction_prompt = f"""Extract product search preferences from the user message. Return ONLY JSON.

Recent conversation:
{history_snippet}

User: "{msg}"

JSON format:
{{"keywords":[],"category":null,"max_price":null,"min_price":null,"min_rating":null,"max_rating":null,"brand":null,"limit":5}}

Rules:
- keywords: core product type only (singular). Examples: "headphone" not "headphones", "earbud" not "earbuds", "tablet" not "tablets", "smartwatch" not "smartwatches".
  Keep compound product names intact: "mixer grinder", "air conditioner", "washing machine", "water purifier", "electric kettle", "rice cooker", "pressure cooker", "coffee maker", "induction cooktop", "noise cancelling headphone", "water bottle".
  For feature-qualified searches, extract just the product type: "lightweight laptop" → ["laptop"], "wireless keyboard" → ["keyboard"], "fast charging cable" → ["cable"], "OLED TV" → ["tv"], "mechanical keyboard" → ["keyboard"].
  Broad intents: kitchen-related → ["kitchen appliance"], home-related → ["home appliance"], energy saving/eco → ["energy saving"].
  Commute/travel intents: "morning commute", "daily commute", "travelling", "on the go", "gym", "workout", "running", "jogging" → ["earbuds"].
  Study/work intents: "studying", "focus", "work from home", "office use", "calls/meetings" → ["headphone"].
  Return [] only if truly no product type is mentioned (e.g. pure rating/price filters with no product context).
- category: "Electronics" for phones/smartwatches/tablets/TVs/headphones/earbuds/ACs/refrigerators/washing machines. "Computers&Accessories" for laptops/monitors/keyboards/printers. "Home&Kitchen" for kitchen appliances, water bottles, pressure cookers. null if unclear or multiple types (e.g. "Apple products").
- max_price/min_price: numeric only (under/below → max_price, above/over → min_price)
- min_rating/max_rating: numeric only. "above 4" → min_rating 4. "below 4.5" → max_rating 4.5. "rated 4 and above" → min_rating 4.
- brand: extract ONLY if the user explicitly names a brand in their message. Do not infer from context.
- limit: number if user says "top N" or "best N". If user says "all" or "show all" or "list all", use 10. Otherwise 5.
- FOLLOW-UP: if message is a short refinement ("only boat", "under 2000", "show cheaper"), carry forward the product type from recent conversation.

Return ONLY valid JSON."""

    try:
        response      = llm.invoke(extraction_prompt)
        text          = response.content.strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.replace("json", "").strip()
                if part.startswith("{"):
                    text = part
                    break
        extracted = _json.loads(text)
        log.info(f"LLM extracted: {extracted}")

        usage         = response.usage_metadata or {}
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = log_llm_span(
            span_name="extract_preferences", prompt_text=extraction_prompt,
            response_text=text, input_tokens=input_tokens,
            output_tokens=output_tokens, model=config.LLM_MODEL,
            prompt_name="extract_preferences", prompt_version=1,
            trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
        )

    except Exception as e:
        log.error(f"LLM extraction failed: {e}")
        extracted     = {"keywords": [], "category": None, "max_price": None,
                         "min_price": None, "min_rating": None, "brand": None, "limit": 5}
        input_tokens  = 0
        output_tokens = 0
        cost          = 0.0

    raw_cat  = extracted.get("category")
    category = _CATEGORY_NORM.get(raw_cat.lower().strip(), None) if raw_cat else None

    prefs = {
        "keywords":   extracted.get("keywords", []),
        "category":   category,
        "max_price":  extracted.get("max_price"),
        "min_price":  extracted.get("min_price"),
        "min_rating": extracted.get("min_rating"),
        "max_rating": extracted.get("max_rating"),
        "brand":      extracted.get("brand"),
        "limit":      extracted.get("limit", 5),
    }

    # Fallback: second focused LLM call when no keywords were extracted
    if not prefs["keywords"]:
        fallback_prompt = f"""The user is asking about a product but the product type wasn't identified.

User message: "{msg}"

What is the single main product they are looking for?
Return ONLY the product name/phrase. No JSON, no explanation, nothing else.

Rules:
- Use the canonical name: "mixer grinder" not "grinder", "air conditioner" not "AC"
- Broad intents: "kitchen gifts / gift for cooking / kitchen items" → kitchen appliance
- Broad intents: "home essentials / new home / must have home" → home appliance
- Energy intents: "energy saving / power saving / eco-friendly" → energy saving
- Context: "for brewing tea / making tea" → electric kettle
- Context: "for coffee / brewing coffee" → coffee maker
- Context: "morning commute / daily commute / travelling / on the go / gym / workout / running / jogging" → earbuds
- Context: "studying / focus / office / work from home / calls / meetings" → headphone
- Context: "home office setup / desk setup / wfh setup" → monitor
- If truly no specific product is implied, return empty string."""

        try:
            fb       = llm.invoke(fallback_prompt)
            fb_usage = fb.usage_metadata or {}
            fb_in    = fb_usage.get("input_tokens",  0)
            fb_out   = fb_usage.get("output_tokens", 0)
            fb_cost  = calculate_cost(config.LLM_MODEL, fb_in, fb_out)
            keyword  = fb.content.strip().lower().strip("\"'")
            if keyword and keyword not in _GENERIC_WORDS:
                prefs["keywords"] = [keyword]
                log.info(f"LLM fallback keyword: {keyword}")
            input_tokens  += fb_in
            output_tokens += fb_out
            cost          += fb_cost
        except Exception as e:
            log.error(f"LLM keyword fallback failed: {e}")

    # Rating filter fallback
    msg_lower = msg.lower()
    if not prefs.get("min_rating"):
        m = re.search(r'(?:above|over|minimum|at least|rated?\s+)(\d+(?:\.\d+)?)\s*(?:star|rating|rated?)?', msg_lower)
        if not m:
            m = re.search(r'(\d+(?:\.\d+)?)\s*(?:star|rating)s?\s*(?:and\s+)?(?:above|over|plus|\+)', msg_lower)
        if m:
            prefs["min_rating"] = float(m.group(1))

    if not prefs.get("max_rating"):
        m = re.search(r'(?:below|under|less than|max(?:imum)?)\s+(\d+(?:\.\d+)?)\s*(?:star|rating|rated?)?', msg_lower)
        if not m:
            m = re.search(r'(\d+(?:\.\d+)?)\s*(?:star|rating)s?\s*(?:and\s+)?(?:below|under)', msg_lower)
        if m:
            prefs["max_rating"] = float(m.group(1))

    # Price filter fallback
    if not prefs.get("max_price"):
        m = re.search(r'(?:below|under|less than|max(?:imum)?)\s+(?:rs\.?\s*|₹\s*|inr\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rs\.?|₹|rupees?|inr)\b', msg_lower)
        if not m:
            m = re.search(r'(?:below|under|less than)\s+(\d{3,}(?:,\d+)*(?:\.\d+)?)\b', msg_lower)
        if m:
            prefs["max_price"] = float(m.group(1).replace(',', ''))

    if not prefs.get("min_price"):
        m = re.search(r'(?:above|over|minimum|at least|more than)\s+(?:rs\.?\s*|₹\s*|inr\s*)?(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rs\.?|₹|rupees?|inr)\b', msg_lower)
        if not m:
            m = re.search(r'(?:above|over|more than)\s+(\d{3,}(?:,\d+)*(?:\.\d+)?)\b', msg_lower)
        if m:
            prefs["min_price"] = float(m.group(1).replace(',', ''))

    if re.search(r'\b(all|every|complete list)\b', msg_lower):
        prefs["limit"] = max(prefs.get("limit", 5), 10)

    # Brand fallback: scan message for known brands if LLM missed it
    if not prefs.get("brand"):
        for token, display in BRAND_MAP.items():
            if re.search(rf'\b{re.escape(token)}\b', msg_lower):
                prefs["brand"] = display
                break

    # Follow-up carry-forward: pull brand/keyword from recent history for filter refinements
    _has_filter = (prefs.get("max_price") or prefs.get("min_price") or
                   prefs.get("min_rating") or prefs.get("max_rating"))
    if _has_filter:
        for hist_m in reversed(recent_msgs):
            hist_content = (hist_m.get("content") or "").lower()
            if not prefs.get("brand"):
                for token, display in BRAND_MAP.items():
                    if re.search(rf'\b{re.escape(token)}\b', hist_content):
                        prefs["brand"] = display
                        log.info(f"Carried forward brand from history: {display}")
                        break
            if not prefs.get("keywords"):
                for pt in _CARRY_PRODUCT_TYPES:
                    if re.search(rf'\b{re.escape(pt)}\b', hist_content):
                        prefs["keywords"] = [pt]
                        log.info(f"Carried forward keyword from history: {pt}")
                        break
            if prefs.get("brand") and prefs.get("keywords"):
                break

    # Strip brand tokens from keywords to prevent duplicate/cross-brand SQL filters
    if prefs.get("brand"):
        brand_lower    = prefs["brand"].lower()
        prefs["keywords"] = [
            k for k in prefs["keywords"]
            if k.lower() != brand_lower and k.lower() not in BRAND_MAP
        ]

    log_tool_span(
        span_name="extract_preferences", tool_name="preference_extractor",
        tool_input={"message": state["current_input"]},
        tool_output={"prefs": str(prefs)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Preferences extracted: {prefs}")
    return {
        **state,
        "search_preferences": prefs,
        "search_retry":       0,
        "total_tokens":       state.get("total_tokens", 0) + input_tokens + output_tokens,
        "total_cost_usd":     state.get("total_cost_usd", 0.0) + cost,
    }


def search_products(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "search_products")
    log.info("Tool called: search_products")

    prefs   = state.get("search_preferences", {})
    retry   = state.get("search_retry", 0)
    results = mock_product_api_call(prefs, retry)

    log_tool_span(
        span_name="search_products", tool_name="product_catalog_db",
        tool_input={"prefs": str(prefs), "retry": retry},
        tool_output={"results_count": len(results)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Found {len(results)} products")
    return {**state, "search_results": results}


def results_found_edge(state: AgentState) -> str:
    results = state.get("search_results", [])
    retry   = state.get("search_retry", 0)
    if results:
        return "rank_and_filter"
    if retry < 2:
        return "broaden_search"
    return "no_results_response"


def broaden_search(state: AgentState) -> AgentState:
    log   = get_log(state["request_id"], "product_agent", "broaden_search")
    prefs = state.get("search_preferences", {})
    retry = state.get("search_retry", 0)

    if retry == 0:
        prefs = {**prefs, "brand": None}
    elif retry == 1:
        if prefs.get("max_price"):
            prefs = {**prefs, "max_price": prefs["max_price"] * 1.5}
        prefs = {**prefs, "category": None}
    elif retry == 2:
        prefs = {**prefs, "keywords": []}

    log.info("Broadening search filters")
    return {**state, "search_preferences": prefs, "search_retry": retry + 1}


def no_results_response(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "no_results_response")
    log.warning("No products found after retries")
    return {
        **state,
        "response": "I could not find any products matching your requirements. Please try with different filters.",
    }


def rank_and_filter(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "rank_and_filter")
    log.info("LLM called")

    results    = state.get("search_results", [])
    user_limit = state.get("search_preferences", {}).get("limit", 5)
    pool_size  = max(user_limit * 2, 6)
    pool       = results[:pool_size]

    products_text = "\n".join([
        f"{i+1}. {p['name']} | Price: ₹{p['price']} | Rating: {p['rating']}"
        for i, p in enumerate(pool)
    ])

    prompt_template = mlflow.genai.load_prompt("prompts:/product_ranking_prompt/1")
    prompt = prompt_template.format(
        user_request=state['current_input'],
        products_text=products_text,
    )

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)

        try:
            order  = [int(x.strip()) - 1 for x in response.content.strip().split(",")]
            ranked = [pool[i] for i in order if i < len(pool)]
        except Exception:
            ranked = pool

    except Exception as e:
        log.warning(f"LLM ranking failed: {e}")
        ranked        = pool
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0
        response      = type("R", (), {"content": ""})()

    log_llm_span(
        span_name="rank_and_filter", prompt_text=prompt,
        response_text=response.content, input_tokens=input_tokens,
        output_tokens=output_tokens, model=config.LLM_MODEL,
        prompt_name="product_ranking_prompt", prompt_version=1,
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Products ranked: {len(ranked)} results")
    return {
        **state,
        "ranked_products":  ranked,
        "total_tokens":     state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd":   state["total_cost_usd"] + cost,
    }


def fetch_reviews(state: AgentState) -> AgentState:
    log      = get_log(state["request_id"], "product_agent", "fetch_reviews")
    products = state.get("ranked_products", [])
    enriched = []

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for p in products:
                    cur.execute(
                        """SELECT review_title, review_text, rating
                           FROM reviews WHERE product_id = %s
                           ORDER BY rating DESC LIMIT 3""",
                        [p["product_id"]]
                    )
                    enriched.append({**p, "reviews": [dict(r) for r in cur.fetchall()]})
    except Exception as e:
        log.error(f"Reviews fetch error: {e}")
        enriched = products

    log_tool_span(
        span_name="fetch_reviews", tool_name="reviews_table",
        tool_input={"product_count": len(products)},
        tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Fetched reviews for {len(enriched)} products")
    return {**state, "enriched_products": enriched}


def fetch_specs(state: AgentState) -> AgentState:
    log      = get_log(state["request_id"], "product_agent", "fetch_specs")
    products = state.get("enriched_products", [])
    enriched = []

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for p in products:
                    cur.execute(
                        """SELECT description, rating, rating_count,
                                  discount_pct, original_price
                           FROM products WHERE product_id = %s""",
                        [p["product_id"]]
                    )
                    row = cur.fetchone()
                    enriched.append({**p, "specs": dict(row)} if row else p)
    except Exception as e:
        log.error(f"Specs fetch error: {e}")
        enriched = products

    log_tool_span(
        span_name="fetch_specs", tool_name="products_specs",
        tool_input={"product_count": len(products)},
        tool_output={"enriched_count": len(enriched)},
        trace_id=state.get("mlflow_trace_id"), parent_id=state.get("mlflow_span_id"),
    )

    log.info(f"Fetched specs for {len(enriched)} products")
    return {**state, "enriched_products": enriched}


def compute_score(state: AgentState) -> AgentState:
    log      = get_log(state["request_id"], "product_agent", "compute_score")
    products = state.get("enriched_products", [])
    scored   = []

    for p in products:
        rating       = float(p.get("rating") or 0)
        review_count = len(p.get("reviews", []))
        price        = float(p.get("price") or 9999)
        orig_price   = float(p.get("original_price") or price)
        discount     = ((orig_price - price) / orig_price * 100) if orig_price > 0 else 0
        score        = (rating / 5 * 40) + (min(review_count, 3) / 3 * 30) + (min(discount, 50) / 50 * 30)
        scored.append({**p, "score": round(score, 2)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"Scored {len(scored)} products")
    return {**state, "enriched_products": scored}


def build_product_enrichment_subgraph():
    sub = StateGraph(AgentState)
    sub.add_node("fetch_reviews", fetch_reviews)
    sub.add_node("fetch_specs",   fetch_specs)
    sub.add_node("compute_score", compute_score)
    sub.set_entry_point("fetch_reviews")
    sub.add_edge("fetch_reviews", "fetch_specs")
    sub.add_edge("fetch_specs",   "compute_score")
    sub.add_edge("compute_score", END)
    return sub.compile()


def _extract_why(desc: str) -> str:
    first = re.split(r'(?<=[.!])\s+', desc.strip())[0].strip()
    if len(first) >= 20:
        return first[:160] + ("…" if len(first) > 160 else "")
    return desc[:160] + ("…" if len(desc) > 160 else "")


def format_recommendations(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "format_recommendations")
    log.info("Node entered")

    limit    = state.get("search_preferences", {}).get("limit", 3)
    products = state.get("enriched_products", [])[:limit]
    if not products:
        return {**state, "response": "No products found matching your criteria."}

    keywords     = state.get("search_preferences", {}).get("keywords", [])
    product_type = keywords[0] if keywords else "product"
    lines        = [f"Here are the top **{product_type}** recommendations for you:\n"]

    for i, p in enumerate(products, 1):
        price  = f"₹{p['price']}"   if p.get("price")  is not None else "Price unavailable"
        rating = f"{p['rating']}/5" if p.get("rating") is not None else "No rating"
        specs  = p.get("specs") or {}
        desc   = (specs.get("description") or p.get("description") or "").strip()
        why    = _extract_why(desc) if desc else "Highly rated option in its category."

        lines.append(f"### {i}. {p['name']}")
        lines.append(f"- **Price:** {price}")
        lines.append(f"- **Rating:** {rating}")
        lines.append(f"- **Why buy it:** {why}")
        lines.append("")

    if len(products) >= 2:
        cheapest  = min(products, key=lambda x: x.get("price") or float("inf"))
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
        "response":       "\n".join(lines),
        "total_tokens":   state["total_tokens"],
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
                "total_tokens":   state["total_tokens"],
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

    graph.add_node("extract_preferences",    extract_preferences)
    graph.add_node("search_products",        search_products)
    graph.add_node("broaden_search",         broaden_search)
    graph.add_node("rank_and_filter",        rank_and_filter)
    graph.add_node("product_enrichment",     build_product_enrichment_subgraph())
    graph.add_node("format_recommendations", format_recommendations)
    graph.add_node("no_results_response",    no_results_response)
    graph.add_node("save_to_db",             save_to_db)

    graph.set_entry_point("extract_preferences")
    graph.add_edge("extract_preferences", "search_products")

    graph.add_conditional_edges("search_products", results_found_edge, {
        "rank_and_filter":     "rank_and_filter",
        "broaden_search":      "broaden_search",
        "no_results_response": "no_results_response",
    })

    graph.add_edge("broaden_search",         "search_products")
    graph.add_edge("rank_and_filter",        "product_enrichment")
    graph.add_edge("product_enrichment",     "format_recommendations")
    graph.add_edge("format_recommendations", "save_to_db")
    graph.add_edge("save_to_db",             END)
    graph.add_edge("no_results_response",    END)

    return graph.compile()


product_agent = build_product_agent()


if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    state  = empty_state(
        session_id=session_id, user_id="test-user",
        request_id="test-req-002", messages=[],
        current_input="find me a good laptop under 60000",
    )
    result = product_agent.invoke(state)
    print(f"\n=== RESULT ===")
    print(f"Response: {result['response']}")
    print(f"Tokens:   {result['total_tokens']}")
    print(f"Cost:     ${result['total_cost_usd']}")
