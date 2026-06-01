"""Unit tests for pipeline.py intent router."""

import pytest  # noqa: F401
from unittest.mock import MagicMock, patch

from helpers import make_state
from pipeline import intent_router, route_to_agent

# ─── route_to_agent ──────────────────────────────────────────────────────────


class TestRouteToAgent:
    def test_order_query(self):
        assert route_to_agent(make_state(intent="order_query")) == "order_query"

    def test_product_query(self):
        assert route_to_agent(make_state(intent="product_query")) == "product_query"

    def test_support_query(self):
        assert route_to_agent(make_state(intent="support_query")) == "support_query"

    def test_returns_none_when_intent_is_none(self):
        # intent key exists but is None → get() returns None (default not used)
        assert route_to_agent(make_state(intent=None)) is None


# ─── intent_router — keyword shortcuts ───────────────────────────────────────


class TestIntentRouterKeywords:
    """These queries should hit the keyword shortcut and bypass the LLM."""

    def _route(self, message):
        state = make_state(current_input=message)
        with patch("pipeline._support_pending", {}):
            result = intent_router(state)
        return result["intent"]

    def test_show_tickets_routes_to_support(self):
        assert self._route("show me the tickets i raised") == "support_query"

    def test_refund_routes_to_support(self):
        assert self._route("i want a refund") == "support_query"

    def test_damaged_routes_to_support(self):
        assert self._route("my laptop arrived damaged") == "support_query"

    def test_cancel_order_routes_to_support(self):
        assert self._route("cancel my order") == "support_query"

    def test_return_order_routes_to_support(self):
        assert self._route("i want to return my order") == "support_query"

    def test_missing_order_routes_to_support(self):
        assert self._route("my order is missing") == "support_query"

    def test_warranty_routes_to_support(self):
        assert self._route("i want to raise a warranty claim") == "support_query"


# ─── intent_router — pending support session ─────────────────────────────────


class TestIntentRouterPending:
    def test_pending_session_routes_to_support_without_llm(self):
        state = make_state(session_id="pending-session", current_input="1")
        with patch("pipeline._support_pending", {"pending-session": {"issue_type": "damaged_goods"}}):
            result = intent_router(state)
        assert result["intent"] == "support_query"


# ─── intent_router — LLM-based routing ───────────────────────────────────────


class TestIntentRouterLLM:
    """Queries that don't match keyword shortcuts should use the LLM."""

    def _route_via_llm(self, message, llm_intent):
        state = make_state(current_input=message)
        mock_result = MagicMock()
        mock_result.intent = llm_intent

        with patch("pipeline._support_pending", {}), patch("pipeline.llm") as mock_llm:
            mock_llm.with_structured_output.return_value.invoke.return_value = mock_result
            result = intent_router(state)

        return result["intent"]

    def test_llm_routes_order_query(self):
        assert self._route_via_llm("where is my order ORD001", "order_query") == "order_query"

    def test_llm_routes_product_query(self):
        assert self._route_via_llm("recommend me a good mouse", "product_query") == "product_query"

    def test_llm_failure_defaults_to_order_query(self):
        state = make_state(current_input="something ambiguous")
        with patch("pipeline._support_pending", {}), patch("pipeline.llm") as mock_llm:
            mock_llm.with_structured_output.return_value.invoke.side_effect = Exception("LLM down")
            result = intent_router(state)

        assert result["intent"] == "order_query"
