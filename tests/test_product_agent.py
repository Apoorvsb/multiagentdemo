"""Unit tests for agents/product_agent.py"""

import pytest  # noqa: F401
from unittest.mock import MagicMock, patch

from helpers import make_state, mock_db

# ─── mock_product_api_call ───────────────────────────────────────────────────


class TestMockProductApiCall:
    """Tests for the FTS-based product search."""

    def _run(self, prefs, rows):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            return mock_product_api_call(prefs)

    def test_returns_empty_when_no_results(self):
        result = self._run({"category": "laptop"}, [])
        assert result == []

    def test_returns_products_matching_category(self):
        row = {
            "product_id": "P001",
            "name": "HP Laptop 15",
            "brand": "HP",
            "category": "laptops",
            "price": 45000.0,
            "rating": 4.2,
            "availability": True,
            "description": "Good laptop",
        }
        result = self._run({"category": "laptop"}, [row])
        assert len(result) == 1
        assert result[0]["name"] == "HP Laptop 15"

    def test_price_passed_as_is(self):
        """mock_product_api_call uses max_price as-is; inflation is handled by broaden_search."""
        from agents.product_agent import mock_product_api_call

        prefs_called = {}
        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur

            def capture_execute(sql, params=None):
                if params:
                    prefs_called["params"] = params

            cur.execute.side_effect = capture_execute
            mock_product_api_call({"max_price": 1000, "category": "mouse"}, retry=1)

        params = prefs_called.get("params", [])
        assert any(p == 1000 for p in params), f"Expected 1000 in params: {params}"

    def test_with_brand_filter(self):
        row = {
            "product_id": "P002",
            "name": "Samsung Galaxy Watch",
            "brand": "Samsung",
            "category": "smartwatch",
            "price": 12000.0,
            "rating": 4.5,
            "availability": True,
            "description": "Smart watch",
        }
        result = self._run({"brand": "Samsung", "category": "smartwatch"}, [row])
        assert result[0]["brand"] == "Samsung"


# ─── extract_preferences ─────────────────────────────────────────────────────


class TestExtractPreferences:
    """Tests for the LLM-based preference extractor with regex fallbacks."""

    def _run(self, state):
        from agents.product_agent import extract_preferences

        return extract_preferences(state)

    def _mock_llm(self, prefs_json: str):
        mock_resp = MagicMock()
        mock_resp.content = prefs_json
        mock_resp.usage_metadata = {"input_tokens": 80, "output_tokens": 20}
        return mock_resp

    def test_basic_extraction(self):
        state = make_state(current_input="find me a laptop under 50000")
        llm_json = (
            '{"search_query": "laptop", "max_price": 50000, "min_price": null, '
            '"category": "Computers&Accessories", "brand": null, "min_rating": null, '
            '"max_rating": null, "sort_by": "relevance", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs["max_price"] == 50000
        assert prefs.get("search_query") or prefs.get("category")

    def test_regex_fallback_extracts_price_when_llm_misses(self):
        state = make_state(current_input="show me headphones below 1500")
        llm_json = (
            '{"search_query": "headphone", "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("max_price") == 1500.0, f"Expected regex to catch 1500 but got {prefs.get('max_price')}"

    def test_brand_carryforward_from_history(self):
        state = make_state(
            current_input="under 70000 rupees",
            messages=[
                {"role": "user", "content": "show me only HP laptops"},
                {"role": "assistant", "content": "Here are HP laptops for you."},
            ],
        )
        llm_json = (
            '{"search_query": null, "max_price": 70000, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        fallback_resp = MagicMock()
        fallback_resp.content = "none"
        fallback_resp.usage_metadata = {"input_tokens": 20, "output_tokens": 2}

        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.side_effect = [
                self._mock_llm(llm_json),  # primary extraction call
                fallback_resp,  # fallback search_query call
            ]
            result = self._run(state)

        prefs = result["search_preferences"]
        assert (
            prefs.get("brand") is not None and "HP" in prefs["brand"]
        ), f"Expected HP brand carry-forward but got: {prefs.get('brand')}"

    def test_llm_failure_returns_empty_preferences(self):
        state = make_state(current_input="find me a keyboard")
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.side_effect = Exception("timeout")
            result = self._run(state)

        prefs = result.get("search_preferences") or {}
        assert isinstance(prefs, dict)

    def test_rating_regex_fallback(self):
        state = make_state(current_input="show me phones 4 stars and above")
        llm_json = (
            '{"search_query": "phone", "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("min_rating") == 4.0, f"Expected 4.0 min_rating from regex but got: {prefs.get('min_rating')}"

    def test_min_price_regex_fallback(self):
        state = make_state(current_input="show me laptops above 40000 rupees")
        llm_json = (
            '{"search_query": "laptop", "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("min_price") == 40000.0, f"Expected 40000 min_price but got: {prefs.get('min_price')}"

    def test_price_and_rating_both_use_above_keyword(self):
        """'kettle above 2000 and above 4.5 ratings' must not confuse price with rating."""
        state = make_state(current_input="kettle above 2000 and above 4.5 ratings")
        # LLM misses both filters to force regex fallbacks
        llm_json = (
            '{"search_query": "electric kettle", "max_price": null, "min_price": null, '
            '"category": "Home&Kitchen", "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("min_price") == 2000.0, f"Expected min_price=2000 but got {prefs.get('min_price')}"
        assert prefs.get("min_rating") == 4.5, f"Expected min_rating=4.5 but got {prefs.get('min_rating')}"
        # min_rating must never be set to a price-like value
        assert (prefs.get("min_rating") or 0) <= 5, "min_rating was set to a price value"

    def test_sort_by_price_asc_for_cheapest(self):
        state = make_state(current_input="cheapest laptop")
        llm_json = (
            '{"search_query": "laptop", "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "price_asc", "limit": 5}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("sort_by") == "price_asc"


# ─── mlflow_helpers.calculate_cost ───────────────────────────────────────────


class TestCalculateCost:
    def test_known_model_cost(self):
        from mlflow_helpers import calculate_cost

        cost = calculate_cost("llama-3.1-8b-instant", 1000, 1000)
        assert isinstance(cost, float)
        assert cost > 0

    def test_unknown_model_uses_default_pricing(self):
        from mlflow_helpers import calculate_cost

        cost = calculate_cost("unknown-model", 1000, 1000)
        assert isinstance(cost, float)
        assert cost > 0

    def test_zero_tokens_gives_zero_cost(self):
        from mlflow_helpers import calculate_cost

        cost = calculate_cost("llama-3.1-8b-instant", 0, 0)
        assert cost == 0.0


# ─── mlflow_helpers span functions ───────────────────────────────────────────


class TestMlflowHelperSpans:
    def test_log_llm_span_returns_cost(self):
        from mlflow_helpers import log_llm_span

        cost = log_llm_span(
            span_name="test_span",
            prompt_text="hello",
            response_text="world",
            input_tokens=100,
            output_tokens=50,
            model="llama-3.1-8b-instant",
            prompt_name="test_prompt",
            prompt_version=1,
        )
        assert isinstance(cost, float)
        assert cost >= 0

    def test_log_tool_span_does_not_raise(self):
        from mlflow_helpers import log_tool_span

        log_tool_span(
            span_name="test_tool",
            tool_name="mock_api",
            tool_input={"key": "value"},
            tool_output={"result": "ok"},
        )


# ─── search_products node ─────────────────────────────────────────────────────


class TestSearchProducts:
    def _import(self):
        from agents.product_agent import search_products, results_found_edge, broaden_search, no_results_response

        return search_products, results_found_edge, broaden_search, no_results_response

    def test_search_products_stores_results(self):
        search_products, _, _, _ = self._import()
        prefs = {"search_query": "laptop", "max_price": 50000}
        state = make_state(search_preferences=prefs, search_retry=0)
        rows = [
            {
                "product_id": "P1",
                "name": "HP Laptop",
                "brand": "HP",
                "category": "laptops",
                "price": 45000.0,
                "rating": 4.2,
                "availability": True,
                "description": "Good",
            }
        ]

        with patch("agents.product_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = search_products(state)

        assert len(result["search_results"]) == 1

    def test_results_found_edge_with_results(self):
        _, results_found_edge, _, _ = self._import()
        state = make_state(search_results=[{"name": "Laptop"}], search_retry=0)
        assert results_found_edge(state) == "rank_and_filter"

    def test_results_found_edge_no_results_retry(self):
        _, results_found_edge, _, _ = self._import()
        state = make_state(search_results=[], search_retry=0)
        assert results_found_edge(state) == "broaden_search"

    def test_results_found_edge_no_results_exhausted(self):
        _, results_found_edge, _, _ = self._import()
        state = make_state(search_results=[], search_retry=2)
        assert results_found_edge(state) == "no_results_response"

    def test_broaden_search_inflates_price(self):
        _, _, broaden_search, _ = self._import()
        state = make_state(
            search_preferences={"search_query": "laptop", "max_price": 1000, "category": "Computers&Accessories"},
            search_retry=1,
        )
        result = broaden_search(state)
        assert result["search_preferences"]["max_price"] == 1500.0
        assert result["search_retry"] == 2

    def test_broaden_search_drops_category_on_second_retry(self):
        _, _, broaden_search, _ = self._import()
        state = make_state(
            search_preferences={"search_query": "laptop", "max_price": None, "category": "Computers&Accessories"},
            search_retry=1,
        )
        result = broaden_search(state)
        assert result["search_preferences"]["category"] is None
        assert result["search_retry"] == 2

    def test_broaden_search_simplifies_query_on_second_retry(self):
        _, _, broaden_search, _ = self._import()
        state = make_state(
            search_preferences={"search_query": "wireless mouse", "max_price": None, "category": None},
            search_retry=1,
        )
        result = broaden_search(state)
        # Last word of "wireless mouse" is "mouse"
        assert result["search_preferences"]["search_query"] == "mouse"

    def test_no_results_response_message(self):
        _, _, _, no_results_response = self._import()
        state = make_state()
        result = no_results_response(state)
        assert "find" in result["response"].lower()

    def test_no_results_response_names_brand_and_product(self):
        _, _, _, no_results_response = self._import()
        state = make_state(
            current_input="HP brand bags",
            search_preferences={"search_query": "bags", "brand": None},  # brand stripped by broaden
        )
        result = no_results_response(state)
        assert "HP" in result["response"]
        assert "bags" in result["response"].lower()

    def test_no_results_search_query_never_cleared_on_retry2(self):
        """retry >= 2 must not clear search_query and return unrelated products."""
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_product_api_call({"search_query": "bags", "brand": "HP"}, retry=2)

        sql = cur.execute.call_args[0][0]
        assert "plainto_tsquery" in sql, "search_query must still be used at retry=2"


# ─── rank_and_filter node ─────────────────────────────────────────────────────


class TestRankAndFilter:
    def test_rank_and_filter_with_llm(self):
        from agents.product_agent import rank_and_filter

        products = [
            {"name": "HP Laptop", "price": 45000, "rating": 4.2, "description": "Good laptop", "brand": "HP"},
            {"name": "Dell Laptop", "price": 50000, "rating": 4.5, "description": "Better laptop", "brand": "Dell"},
        ]
        state = make_state(
            search_results=products,
            search_preferences={"limit": 5},
            current_input="find me a laptop",
        )
        mock_resp = MagicMock()
        mock_resp.content = "2,1"
        mock_resp.usage_metadata = {"input_tokens": 60, "output_tokens": 5}

        with patch("agents.product_agent.llm") as mock_llm, patch("agents.product_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.return_value = mock_resp
            result = rank_and_filter(state)

        assert result["ranked_products"] is not None
        assert len(result["ranked_products"]) > 0

    def test_rank_and_filter_llm_failure_falls_back(self):
        from agents.product_agent import rank_and_filter

        products = [{"name": "Laptop A", "price": 40000, "rating": 4.0, "description": "ok", "brand": "HP"}]
        state = make_state(
            search_results=products,
            search_preferences={"limit": 5},
            current_input="find me a laptop",
        )
        with patch("agents.product_agent.llm") as mock_llm, patch("agents.product_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.side_effect = Exception("LLM unavailable")
            result = rank_and_filter(state)

        assert result["ranked_products"] == products


# ─── mock_product_api_call with search_query ─────────────────────────────────


class TestMockProductApiCallSearchQuery:
    def test_search_query_builds_fts_condition(self):
        from agents.product_agent import mock_product_api_call

        rows = [
            {
                "product_id": "P5",
                "name": "Samsung Galaxy S24",
                "brand": "Samsung",
                "category": "Electronics",
                "price": 75000.0,
                "rating": 4.6,
                "availability": True,
                "description": "Flagship phone",
            }
        ]
        with patch("agents.product_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = mock_product_api_call({"search_query": "phone"})
        assert len(result) == 1

    def test_search_query_sql_contains_tsquery(self):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_product_api_call({"search_query": "wireless mouse"})

        assert cur.execute.called
        sql_called = cur.execute.call_args[0][0]
        assert "plainto_tsquery" in sql_called

    def test_sort_by_price_asc_uses_price_order(self):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_product_api_call({"search_query": "laptop", "sort_by": "price_asc"})

        sql_called = cur.execute.call_args[0][0]
        assert "price ASC" in sql_called

    def test_retry_simplifies_search_query(self):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            # retry=1 → "wireless mouse" becomes "mouse"
            mock_product_api_call({"search_query": "wireless mouse"}, retry=1)

        params = cur.execute.call_args[0][1]
        assert "mouse" in params, f"Expected simplified query 'mouse' in params: {params}"


# ─── comparison & brands helpers ────────────────────────────────────────────


class TestHandleComparison:
    def test_comparison_detected_and_routed(self):
        from agents.product_agent import extract_preferences

        state = make_state(current_input="compare Sony WH-1000XM5 vs Bose QC45")
        p1 = {
            "product_id": "p1",
            "name": "Sony WH-1000XM5",
            "brand": "Sony",
            "price": 24999,
            "rating": 4.7,
            "description": "Sony ANC headphone",
            "category": "Electronics",
            "original_price": 29999,
            "discount_pct": "17%",
            "rating_count": "5000",
            "availability": True,
        }
        p2 = {
            "product_id": "p2",
            "name": "Bose QC45",
            "brand": "Bose",
            "price": 29999,
            "rating": 4.6,
            "description": "Bose noise cancelling",
            "category": "Electronics",
            "original_price": 34999,
            "discount_pct": "14%",
            "rating_count": "3000",
            "availability": True,
        }

        mock_resp = MagicMock()
        mock_resp.content = (
            "**Sony WH-1000XM5**\n• Better value\n\n**Bose QC45**\n• Premium build\n\n"
            "**Our Pick: Sony WH-1000XM5** — better price."
        )
        mock_resp.usage_metadata = {"input_tokens": 200, "output_tokens": 50}

        with patch("agents.product_agent.get_conn") as mock_gc, patch("agents.product_agent.llm") as mock_llm:
            cur = MagicMock()
            cur.fetchone.side_effect = [p1, p2]
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_llm.invoke.return_value = mock_resp
            result = extract_preferences(state)

        assert result.get("response") is not None
        assert result.get("search_preferences") is None

    def test_comparison_clarification_when_unparseable(self):
        from agents.product_agent import extract_preferences

        state = make_state(current_input="compare something")
        with patch("agents.product_agent.get_conn"):
            result = extract_preferences(state)

        assert result.get("response") is not None
        assert "compare" in result["response"].lower() or "phrase" in result["response"].lower()

    def test_comparison_one_product_not_found(self):
        from agents.product_agent import _handle_comparison

        state = make_state(current_input="compare wireless mouse vs gaming keyboard")
        p1 = {
            "product_id": "p1",
            "name": "Logitech G102 Gaming Mouse",
            "brand": "Logitech",
            "price": 1495,
            "rating": 4.5,
            "description": "Gaming mouse",
            "category": "Computers&Accessories",
            "original_price": 1795,
            "discount_pct": "17%",
            "rating_count": "10000",
            "availability": True,
        }

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchone.side_effect = [p1, None]
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            result = _handle_comparison(state)

        assert result.get("response") is not None
        assert "couldn't find" in result["response"].lower() or "catalog" in result["response"].lower()

    def test_comparison_both_not_found(self):
        from agents.product_agent import _handle_comparison

        state = make_state(current_input="compare drone vs jetpack")
        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchone.return_value = None
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            result = _handle_comparison(state)

        assert "couldn't find" in result["response"].lower()


class TestHandleBrandsListing:
    def test_brands_query_detected(self):
        from agents.product_agent import extract_preferences

        state = make_state(current_input="what brands do you have")
        rows = [
            {"brand": "Sony", "category": "Electronics", "cnt": 10},
            {"brand": "Dell", "category": "Computers&Accessories", "cnt": 8},
            {"brand": "Prestige", "category": "Home&Kitchen", "cnt": 5},
        ]
        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = rows
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            result = extract_preferences(state)

        assert result.get("response") is not None
        assert "Sony" in result["response"]
        assert "Dell" in result["response"]

    def test_brands_listing_no_db_results(self):
        from agents.product_agent import _handle_brands_listing

        state = make_state(current_input="what brands do you have")
        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            result = _handle_brands_listing(state)

        assert result.get("response") is not None


# ─── new arrivals (sort_by "new") ────────────────────────────────────────────


class TestNewArrivals:
    def test_sort_by_new_regex_for_latest(self):
        from agents.product_agent import extract_preferences

        state = make_state(current_input="show me the latest laptops")
        llm_json = (
            '{"search_query": "laptop", "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null, '
            '"sort_by": "relevance", "limit": 5}'
        )
        mock_resp = MagicMock()
        mock_resp.content = llm_json
        mock_resp.usage_metadata = {"input_tokens": 50, "output_tokens": 10}
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = mock_resp
            result = extract_preferences(state)

        assert result["search_preferences"]["sort_by"] == "new"

    def test_sort_by_new_uses_created_at_order(self):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_product_api_call({"search_query": "laptop", "sort_by": "new"})

        sql = cur.execute.call_args[0][0]
        assert "created_at" in sql.lower()

    def test_new_arrivals_pattern_detection(self):
        from agents.product_agent import extract_preferences

        state = make_state(current_input="new arrivals in electronics")
        llm_json = (
            '{"search_query": null, "max_price": null, "min_price": null, '
            '"category": "Electronics", "brand": null, "min_rating": null, '
            '"max_rating": null, "sort_by": "relevance", "limit": 5}'
        )
        mock_resp = MagicMock()
        mock_resp.content = llm_json
        mock_resp.usage_metadata = {"input_tokens": 50, "output_tokens": 10}
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = mock_resp
            result = extract_preferences(state)

        assert result["search_preferences"]["sort_by"] == "new"
