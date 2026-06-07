"""Unit tests for agents/support_agent.py"""

import pytest  # noqa: F401
from unittest.mock import MagicMock, patch

from helpers import make_state, mock_db
from agents.support_agent import (
    classify_issue,
    assess_severity,
    severity_edge,
    lookup_policy,
    assign_priority,
    create_ticket,
    draft_resolution,
    generate_escalation_response,
    list_tickets_response,
    classify_issue_edge,
    _fetch_delivered_orders,
    _fetch_user_tickets,
    _support_pending,
    _VALID_ISSUE_TYPES,
    _KEYWORD_OVERRIDES,
)

# ─── classify_issue ──────────────────────────────────────────────────────────


class TestClassifyIssue:
    def test_keyword_override_damaged_goods(self):
        state = make_state(current_input="my laptop arrived with a cracked screen")
        result = classify_issue(state)
        assert result["issue_type"] == "damaged_goods"

    def test_keyword_override_show_tickets(self):
        state = make_state(current_input="show me the tickets i raised")
        result = classify_issue(state)
        assert result["issue_type"] == "show_tickets"

    def test_keyword_override_missing_item(self):
        state = make_state(current_input="my order is missing")
        result = classify_issue(state)
        assert result["issue_type"] == "missing_item"

    def test_keyword_override_cancellation(self):
        state = make_state(current_input="i want to cancel my order")
        result = classify_issue(state)
        assert result["issue_type"] == "cancellation_request"

    def test_keyword_override_refund(self):
        state = make_state(current_input="i want a refund for my order")
        result = classify_issue(state)
        assert result["issue_type"] == "refund_request"

    def test_llm_path_valid_response(self):
        state = make_state(current_input="my account is having login issues")
        mock_resp = MagicMock()
        mock_resp.content = "account_issue"
        mock_resp.usage_metadata = {"input_tokens": 60, "output_tokens": 5}

        with patch("agents.support_agent.llm") as mock_llm, patch("agents.support_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.return_value = mock_resp
            result = classify_issue(state)

        assert result["issue_type"] == "account_issue"

    def test_llm_invalid_response_falls_back_to_general_complaint(self):
        state = make_state(current_input="something weird happened")
        mock_resp = MagicMock()
        mock_resp.content = "totally_unknown_type"
        mock_resp.usage_metadata = {"input_tokens": 40, "output_tokens": 5}

        with patch("agents.support_agent.llm") as mock_llm, patch("agents.support_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.return_value = mock_resp
            result = classify_issue(state)

        assert result["issue_type"] == "general_complaint"

    def test_pending_order_selection_by_number(self):
        session_id = "sel-session"
        orders = [
            {
                "order_id": "ORD001",
                "items": "Laptop",
                "sales_per_customer": 50000,
                "order_date": "2025-01-01",
                "status": "DELIVERED",
            },
        ]
        _support_pending[session_id] = {
            "original_message": "my laptop arrived damaged",
            "delivered_orders": orders,
            "issue_type": "damaged_goods",
        }
        state = make_state(session_id=session_id, current_input="1")
        try:
            result = classify_issue(state)
            assert result["order_id"] == "ORD001"
            assert result["issue_type"] == "damaged_goods"
        finally:
            _support_pending.pop(session_id, None)

    def test_valid_issue_types_set_is_complete(self):
        assert "damaged_goods" in _VALID_ISSUE_TYPES
        assert "show_tickets" in _VALID_ISSUE_TYPES
        assert "general_complaint" in _VALID_ISSUE_TYPES
        assert len(_VALID_ISSUE_TYPES) >= 14


# ─── assess_severity ─────────────────────────────────────────────────────────


class TestAssessSeverity:
    def test_damaged_goods_is_high(self):
        state = make_state(issue_type="damaged_goods")
        result = assess_severity(state)
        assert result["severity"] == "HIGH"

    def test_refund_request_is_medium(self):
        state = make_state(issue_type="refund_request")
        result = assess_severity(state)
        assert result["severity"] == "MEDIUM"

    def test_general_complaint_is_low(self):
        state = make_state(issue_type="general_complaint")
        result = assess_severity(state)
        assert result["severity"] == "LOW"

    def test_missing_item_is_high(self):
        state = make_state(issue_type="missing_item")
        result = assess_severity(state)
        assert result["severity"] == "HIGH"

    def test_cancellation_is_medium(self):
        state = make_state(issue_type="cancellation_request")
        result = assess_severity(state)
        assert result["severity"] == "MEDIUM"


# ─── severity_edge ───────────────────────────────────────────────────────────


class TestSeverityEdge:
    def test_high_routes_to_escalation(self):
        state = make_state(severity="HIGH")
        assert severity_edge(state) == "escalation_handler"

    def test_pending_order_routes_to_escalation(self):
        state = make_state(severity="MEDIUM", order_id="__PENDING__")
        assert severity_edge(state) == "escalation_handler"

    def test_medium_without_pending_routes_to_draft(self):
        state = make_state(severity="MEDIUM", order_id=None)
        assert severity_edge(state) == "draft_resolution"

    def test_low_routes_to_draft(self):
        state = make_state(severity="LOW")
        assert severity_edge(state) == "draft_resolution"


# ─── lookup_policy ───────────────────────────────────────────────────────────


class TestLookupPolicy:
    def test_policy_found_for_issue_type(self):
        import json
        from langchain_core.messages import ToolMessage

        state = make_state(
            issue_type="damaged_goods",
            severity="HIGH",
            order_id="ORD001",
        )
        policy_row = {
            "issue_type": "damaged_goods",
            "sla_hours": 24,
            "resolution": "Replace or refund",
        }
        tool_msg = ToolMessage(content=json.dumps(policy_row), tool_call_id="call_1")
        with patch("agents.support_agent.support_tool_node") as mock_tn:
            mock_tn.invoke.return_value = {"messages": [tool_msg]}
            result = lookup_policy(state)

        assert result["policy"] == policy_row

    def test_no_policy_falls_back_to_general(self):
        import json
        from langchain_core.messages import ToolMessage

        state = make_state(
            issue_type="unknown_issue",
            severity="LOW",
            order_id="ORD002",
        )
        fallback_policy = {"issue_type": "general_complaint", "sla_hours": 48}
        tool_msg = ToolMessage(content=json.dumps(fallback_policy), tool_call_id="call_1")
        with patch("agents.support_agent.support_tool_node") as mock_tn:
            mock_tn.invoke.return_value = {"messages": [tool_msg]}
            result = lookup_policy(state)

        assert result["policy"] == fallback_policy


# ─── DB helper functions ─────────────────────────────────────────────────────


class TestFetchHelpers:
    def test_fetch_delivered_orders_returns_list(self):
        rows = [
            {
                "order_id": "ORD001",
                "items": "Laptop",
                "sales_per_customer": 50000,
                "order_date": "2025-01-01",
                "status": "DELIVERED",
            },
        ]
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = _fetch_delivered_orders("test@example.com")

        assert len(result) == 1
        assert result[0]["order_id"] == "ORD001"

    def test_fetch_delivered_orders_returns_empty_on_error(self):
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_gc.side_effect = Exception("DB unavailable")
            result = _fetch_delivered_orders("test@example.com")

        assert result == []

    def test_fetch_user_tickets_returns_list(self):
        rows = [
            {
                "ticket_id": "TKT001",
                "issue_type": "damaged_goods",
                "priority": "HIGH",
                "status": "Open",
                "created_at": "2025-01-10T10:00:00",
                "description": "Cracked screen [Order: ORD001]",
            },
        ]
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = _fetch_user_tickets("test@example.com")

        assert len(result) == 1
        assert result[0]["ticket_id"] == "TKT001"

    def test_fetch_user_tickets_returns_empty_on_error(self):
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_gc.side_effect = Exception("DB down")
            result = _fetch_user_tickets("test@example.com")

        assert result == []


# ─── classify_issue_edge ─────────────────────────────────────────────────────


class TestClassifyIssueEdge:
    def test_show_tickets_routes_to_list(self):
        state = make_state(issue_type="show_tickets")
        assert classify_issue_edge(state) == "list_tickets_response"

    def test_other_issue_routes_to_assess_severity(self):
        state = make_state(issue_type="damaged_goods")
        assert classify_issue_edge(state) == "assess_severity"

    def test_none_issue_routes_to_assess_severity(self):
        state = make_state(issue_type=None)
        assert classify_issue_edge(state) == "assess_severity"


# ─── assign_priority ─────────────────────────────────────────────────────────


class TestAssignPriority:
    def test_high_severity_no_history_gives_priority_2(self):
        state = make_state(severity="HIGH", ticket_count=0)
        result = assign_priority(state)
        assert result["priority"] == "PRIORITY_2"

    def test_high_severity_repeat_gives_priority_1(self):
        state = make_state(severity="HIGH", ticket_count=3)
        result = assign_priority(state)
        assert result["priority"] == "PRIORITY_1"

    def test_medium_severity_gives_priority_3(self):
        state = make_state(severity="MEDIUM", ticket_count=0)
        result = assign_priority(state)
        assert result["priority"] == "PRIORITY_3"

    def test_low_severity_gives_priority_4(self):
        state = make_state(severity="LOW", ticket_count=0)
        result = assign_priority(state)
        assert result["priority"] == "PRIORITY_4"

    def test_pending_order_skips_priority(self):
        state = make_state(severity="HIGH", order_id="__PENDING__", ticket_count=0)
        result = assign_priority(state)
        # Should return state unchanged when awaiting order selection
        assert result.get("priority") is None


# ─── create_ticket ───────────────────────────────────────────────────────────


class TestCreateTicket:
    def test_ticket_created_and_id_returned(self):
        import json
        from langchain_core.messages import ToolMessage

        state = make_state(
            issue_type="damaged_goods",
            severity="HIGH",
            priority="PRIORITY_2",
            order_id="ORD001",
        )
        ticket_payload = {"ticket_id": "TKT_TEST_001", "status": "Open"}
        tool_msg = ToolMessage(content=json.dumps(ticket_payload), tool_call_id="call_1")
        with patch("agents.support_agent.support_tool_node") as mock_tn:
            mock_tn.invoke.return_value = {"messages": [tool_msg]}
            result = create_ticket(state)
        assert result["ticket_id"] is not None
        assert result["ticket_id"] != "TKT_ERROR"

    def test_db_error_returns_tkt_error(self):
        state = make_state(
            issue_type="refund_request",
            severity="MEDIUM",
            priority="PRIORITY_3",
        )
        with patch("agents.support_agent.support_tool_node") as mock_tn:
            mock_tn.invoke.side_effect = Exception("DB unavailable")
            result = create_ticket(state)
        assert result["ticket_id"] == "TKT_ERROR"

    def test_skips_when_order_pending(self):
        state = make_state(order_id="__PENDING__", issue_type="damaged_goods")
        result = create_ticket(state)
        assert result.get("ticket_id") is None


# ─── draft_resolution ────────────────────────────────────────────────────────


class TestDraftResolution:
    def test_llm_response_stored(self):
        state = make_state(
            issue_type="technical_issue",
            severity="LOW",
            current_input="my mouse stopped working",
        )
        mock_resp = MagicMock()
        mock_resp.content = "We apologize and will resolve within 48 hours."
        mock_resp.usage_metadata = {"input_tokens": 100, "output_tokens": 30}

        with patch("agents.support_agent.llm") as mock_llm, patch("agents.support_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.return_value = mock_resp
            result = draft_resolution(state)

        assert "48 hours" in result["response"]
        assert result["total_tokens"] == 130

    def test_llm_failure_uses_fallback_message(self):
        state = make_state(
            issue_type="general_complaint",
            severity="LOW",
            ticket_id="TKT001",
        )
        with patch("agents.support_agent.llm") as mock_llm, patch("agents.support_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.side_effect = Exception("LLM timeout")
            result = draft_resolution(state)

        assert result["response"] is not None
        assert "TKT001" in result["response"]


# ─── generate_escalation_response ────────────────────────────────────────────


class TestGenerateEscalationResponse:
    def test_pending_order_shows_order_list(self):
        session_id = "esc-session"
        orders = [
            {"order_id": "ORD001", "items": '["Laptop"]', "sales_per_customer": 50000, "status": "DELIVERED"},
        ]
        _support_pending[session_id] = {"delivered_orders": orders, "issue_type": "damaged_goods"}
        state = make_state(session_id=session_id, order_id="__PENDING__")
        try:
            result = generate_escalation_response(state)
        finally:
            _support_pending.pop(session_id, None)

        assert "ORD001" in result["response"]

    def test_llm_response_for_normal_escalation(self):
        state = make_state(
            issue_type="damaged_goods",
            severity="HIGH",
            priority="PRIORITY_2",
            ticket_id="TKT999",
            previous_tickets=[],
            order_id="ORD001",
        )
        mock_resp = MagicMock()
        mock_resp.content = "Your complaint has been escalated with ticket TKT999."
        mock_resp.usage_metadata = {"input_tokens": 80, "output_tokens": 25}

        with patch("agents.support_agent.llm") as mock_llm, patch("agents.support_agent.mlflow") as mock_mf:
            mock_mf.genai.load_prompt.return_value.format.return_value = "prompt"
            mock_llm.invoke.return_value = mock_resp
            result = generate_escalation_response(state)

        assert "TKT999" in result["response"]


# ─── list_tickets_response ───────────────────────────────────────────────────


class TestListTicketsResponse:
    def test_no_tickets_message(self):
        state = make_state(user_id="test@example.com")
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = list_tickets_response(state)
        assert "haven't raised" in result["response"] or "no" in result["response"].lower()

    def test_lists_tickets_with_order_ids(self):
        from datetime import datetime

        rows = [
            {
                "ticket_id": "TKT001",
                "order_id": "ORD001",
                "issue_type": "damaged_goods",
                "priority": "HIGH",
                "status": "Open",
                "created_at": datetime(2025, 1, 10),
                "description": "Screen cracked",
            },
        ]
        state = make_state(user_id="test@example.com")
        with patch("agents.support_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = list_tickets_response(state)
        assert "TKT001" in result["response"]
        assert "ORD001" in result["response"]
