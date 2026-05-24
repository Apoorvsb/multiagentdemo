import re
import mlflow
import psycopg2
import psycopg2.extras
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

from state import AgentState
from config import config
from logger import get_log
from mlflow_helpers import calculate_cost, log_llm_span, log_tool_span
from database import get_conn, save_message


llm = ChatGroq(model=config.LLM_MODEL, temperature=0, api_key=config.GROQ_API_KEY)


def extract_preferences(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "extract_preferences")
    log.info("Node entered")

    msg   = state["current_input"].lower()
    prefs = {
        "category":  None,
        "max_price": None,
        "min_price": None,
        "brand":     None,
        "keywords":  [],
    }

    price_match = re.search(r'under\s+(?:rs\.?|₹|inr)?\s*(\d+)', msg)
    if price_match:
        prefs["max_price"] = float(price_match.group(1))

    price_match2 = re.search(r'(?:rs\.?|₹|inr)?\s*(\d+)\s*(?:to|-)\s*(?:rs\.?|₹|inr)?\s*(\d+)', msg)
    if price_match2:
        prefs["min_price"] = float(price_match2.group(1))
        prefs["max_price"] = float(price_match2.group(2))

    categories = {
        "laptop":    "Computers&Accessories",
        "phone":     "Electronics",
        "mobile":    "Electronics",
        "headphone": "Electronics",
        "earphone":  "Electronics",
        "tablet":    "Computers&Accessories",
        "camera":    "Electronics",
        "keyboard":  "Computers&Accessories",
        "mouse":     "Computers&Accessories",
        "cable":     "Computers&Accessories",
        "charger":   "Computers&Accessories",
        "speaker":   "Electronics",
        "watch":     "Electronics",
        "printer":   "Computers&Accessories",
    }
    for keyword, category in categories.items():
        if keyword in msg:
            prefs["category"] = category
            prefs["keywords"].append(keyword)

    log_tool_span(
        span_name   = "extract_preferences",
        tool_name   = "preference_extractor",
        tool_input  = {"message": state["current_input"]},
        tool_output = {"prefs": str(prefs)},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
    )

    log.info(f"Preferences extracted: {prefs}")
    return {**state, "search_preferences": prefs, "search_retry": 0}


def search_products(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "search_products")
    log.info("Tool called: search_products")

    prefs   = state.get("search_preferences", {})
    retry   = state.get("search_retry", 0)
    results = []

    max_price = prefs.get("max_price")
    if max_price and retry > 0:
        max_price = max_price * (1 + 0.3 * retry)

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

                if prefs.get("keywords"):
                    keyword_conditions = " OR ".join(["name ILIKE %s" for _ in prefs["keywords"]])
                    conditions.append(f"({keyword_conditions})")
                    params.extend([f"%{k}%" for k in prefs["keywords"]])

                where = " AND ".join(conditions)
                query = f"SELECT * FROM products WHERE {where} ORDER BY rating DESC NULLS LAST LIMIT 20"
                cur.execute(query, params)
                results = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        log.error(f"Product search error: {e}")

    log_tool_span(
        span_name   = "search_products",
        tool_name   = "postgresql_products_table",
        tool_input  = {"prefs": str(prefs), "retry": retry},
        tool_output = {"results_count": len(results)},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
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

    if prefs.get("max_price") and retry == 0:
        prefs = {**prefs, "max_price": prefs["max_price"] * 1.5}
    elif prefs.get("category") and retry == 1:
        prefs = {**prefs, "category": None}

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

    results = state.get("search_results", [])
    top5    = results[:5]

    products_text = "\n".join([
        f"{i+1}. {p['name']} | Price: ₹{p['price']} | Rating: {p['rating']}"
        for i, p in enumerate(top5)
    ])

    prompt_template = mlflow.genai.load_prompt("prompts:/product_ranking_prompt/1")
    prompt = prompt_template.format(
        user_request  = state['current_input'],
        products_text = products_text,
    )

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)

        try:
            order  = [int(x.strip()) - 1 for x in response.content.strip().split(",")]
            ranked = [top5[i] for i in order if i < len(top5)]
        except Exception:
            ranked = top5

    except Exception as e:
        log.warning(f"LLM ranking failed: {e}")
        ranked        = top5
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0
        response      = type("R", (), {"content": ""})()

    log_llm_span(
        span_name      = "rank_and_filter",
        prompt_text    = prompt,
        response_text  = response.content,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "product_ranking_prompt",
        prompt_version = 1,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

    log.info(f"Products ranked: {len(ranked)} results")
    return {
        **state,
        "ranked_products": ranked,
        "total_tokens":    state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd":  state["total_cost_usd"] + cost,
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
                    reviews = [dict(r) for r in cur.fetchall()]
                    enriched.append({**p, "reviews": reviews})
    except Exception as e:
        log.error(f"Reviews fetch error: {e}")
        enriched = products

    log_tool_span(
        span_name   = "fetch_reviews",
        tool_name   = "postgresql_reviews_table",
        tool_input  = {"product_count": len(products)},
        tool_output = {"enriched_count": len(enriched)},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
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
        span_name   = "fetch_specs",
        tool_name   = "postgresql_products_specs",
        tool_input  = {"product_count": len(products)},
        tool_output = {"enriched_count": len(enriched)},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
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


def format_recommendations(state: AgentState) -> AgentState:
    log      = get_log(state["request_id"], "product_agent", "format_recommendations")
    log.info("LLM called")

    products = state.get("enriched_products", [])[:3]
    if not products:
        return {**state, "response": "No products found matching your criteria."}

    products_text = ""
    for i, p in enumerate(products, 1):
        reviews_text = " ".join([
            f'"{r["review_title"]}"' for r in p.get("reviews", [])[:2]
            if r.get("review_title")
        ])
        products_text += f"\n{i}. {p['name']}\n   Price: ₹{p['price']} | Rating: {p['rating']}/5\n   {reviews_text}\n"

    prompt_template = mlflow.genai.load_prompt("prompts:/format_recommendations_prompt/1")
    prompt = prompt_template.format(
        user_request  = state['current_input'],
        products_text = products_text,
    )

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        content       = response.content
    except Exception as e:
        log.error(f"Format recommendations failed: {e}")
        content       = "Here are some products matching your requirements."
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0

    log_llm_span(
        span_name      = "format_recommendations",
        prompt_text    = prompt,
        response_text  = content,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "format_recommendations_prompt",
        prompt_version = 1,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

    log.info("Recommendations formatted")
    return {
        **state,
        "response":       content,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "product_agent", "save_to_db")
    log.info("Saving response to DB")
    save_message(
        session_id    = state["session_id"],
        role          = "assistant",
        content       = state["response"],
        agent_name    = "product_agent",
        token_usage   = {
            "total_tokens":   state["total_tokens"],
            "total_cost_usd": state["total_cost_usd"],
        },
        mlflow_run_id = state.get("mlflow_run_id"),
    )
    log.info("Response saved")
    return state


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

    state = empty_state(
        session_id    = session_id,
        user_id       = "test-user",
        request_id    = "test-req-002",
        messages      = [],
        current_input = "find me a good cable under 500 rupees",
    )

    result = product_agent.invoke(state)
    print(f"\n=== RESULT ===")
    print(f"Response: {result['response']}")
    print(f"Tokens:   {result['total_tokens']}")
    print(f"Cost:     ${result['total_cost_usd']}")