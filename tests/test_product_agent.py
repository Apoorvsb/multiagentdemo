"""Unit tests for agents/product_agent.py"""

import pytest  # noqa: F401
from unittest.mock import MagicMock, patch

from helpers import make_state, mock_db

# ─── mock_product_api_call ───────────────────────────────────────────────────


class TestMockProductApiCall:
    """Tests for the DB-backed product search."""

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

    def test_price_inflation_on_retry(self):
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
            '{"keywords": ["laptop"], "max_price": 50000, "min_price": null, '
            '"category": "laptops", "brand": null, "min_rating": null, "max_rating": null}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs["max_price"] == 50000
        assert "laptop" in prefs.get("keywords", []) or prefs.get("category") == "laptops"

    def test_regex_fallback_extracts_price_when_llm_misses(self):
        state = make_state(current_input="show me headphones below 1500")
        llm_json = (
            '{"keywords": ["headphones"], "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null}'
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
            '{"keywords": null, "max_price": 70000, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
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
        # Should not crash; preferences may be empty/default
        assert isinstance(prefs, dict)

    def test_rating_regex_fallback(self):
        # Pattern "4 stars and above" matches the fallback regex in extract_preferences
        state = make_state(current_input="show me phones 4 stars and above")
        llm_json = (
            '{"keywords": ["phone"], "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("min_rating") == 4.0, f"Expected 4.0 min_rating from regex but got: {prefs.get('min_rating')}"

    def test_min_price_regex_fallback(self):
        state = make_state(current_input="show me laptops above 40000 rupees")
        llm_json = (
            '{"keywords": ["laptop"], "max_price": null, "min_price": null, '
            '"category": null, "brand": null, "min_rating": null, "max_rating": null}'
        )
        with patch("agents.product_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = self._mock_llm(llm_json)
            result = self._run(state)

        prefs = result["search_preferences"]
        assert prefs.get("min_price") == 40000.0, f"Expected 40000 min_price but got: {prefs.get('min_price')}"


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
        prefs = {"category": "laptop", "max_price": 50000}
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
        state = make_state(search_preferences={"max_price": 1000, "category": "laptop"}, search_retry=1)
        result = broaden_search(state)
        assert result["search_preferences"]["max_price"] == 1500.0
        assert result["search_retry"] == 2

    def test_broaden_search_drops_category_on_second_retry(self):
        _, _, broaden_search, _ = self._import()
        state = make_state(search_preferences={"max_price": None, "category": "laptop"}, search_retry=1)
        result = broaden_search(state)
        assert result["search_preferences"]["category"] is None
        assert result["search_retry"] == 2

    def test_no_results_response_message(self):
        _, _, _, no_results_response = self._import()
        state = make_state()
        result = no_results_response(state)
        assert "could not find" in result["response"].lower()


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


# ─── mock_product_api_call with keywords ─────────────────────────────────────


class TestMockProductApiCallKeywords:
    def test_phone_keyword_uses_phone_patterns(self):
        from agents.product_agent import mock_product_api_call

        rows = [
            {
                "product_id": "P5",
                "name": "Samsung Galaxy S24",
                "brand": "Samsung",
                "category": "smartphones",
                "price": 75000.0,
                "rating": 4.6,
                "availability": True,
                "description": "Flagship phone",
            }
        ]
        with patch("agents.product_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = mock_product_api_call({"keywords": ["phone"]})
        assert len(result) == 1

    def test_laptop_keyword_excludes_accessories(self):
        from agents.product_agent import mock_product_api_call

        with patch("agents.product_agent.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_product_api_call({"keywords": ["laptop"]})
        # Just verify the call doesn't crash and SQL is built
        assert cur.execute.called
