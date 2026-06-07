"""Unit tests for agents/order_agent.py"""

import pytest  # noqa: F401
from unittest.mock import MagicMock, patch

from helpers import make_state, mock_db
from agents.order_agent import (
    group_orders_by_status,
    validate_input,
    validate_input_edge,
    order_found_edge,
    error_response,
    _fetch_order_data_impl,
    generate_response,
    save_to_db,
)

# ─── group_orders_by_status ──────────────────────────────────────────────────


class TestGroupOrdersByStatus:
    def _order(self, oid, status):
        return {
            "order_id": oid,
            "status": status,
            "carrier": "FedEx",
            "estimated_delivery": "2025-01-01",
            "sales_per_customer": 999,
            "items": "Laptop",
        }

    def test_empty_list(self):
        assert group_orders_by_status([]) == ""

    def test_single_delivered(self):
        out = group_orders_by_status([self._order("ORD001", "DELIVERED")])
        assert "DELIVERED" in out
        assert "ORD001" in out

    def test_priority_order_delayed_before_delivered(self):
        orders = [self._order("ORD002", "DELIVERED"), self._order("ORD001", "DELAYED")]
        out = group_orders_by_status(orders)
        assert out.index("DELAYED") < out.index("DELIVERED")

    def test_unknown_status_appended(self):
        out = group_orders_by_status([self._order("ORD003", "CANCELLED")])
        assert "ORD003" in out


# ─── validate_input ──────────────────────────────────────────────────────────


class TestValidateInput:
    def test_guest_user_blocked(self):
        state = make_state(user_id="anon@guest.com", current_input="where is my order")
        result = validate_input(state)
        assert result["response"] is not None
        assert "access" in result["response"].lower() or "sign up" in result["response"].lower()
        assert result["order_id"] is None

    def test_explicit_ord_id_extracted(self):
        state = make_state(current_input="status of ORD12345")
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = validate_input(state)
        assert result["order_id"] == "ORD12345"
        assert result["status_filter"] is None

    def test_follow_up_reuses_previous_order_id(self):
        state = make_state(
            current_input="when will it arrive?",
            messages=[
                {"role": "user", "content": "where is my order"},
                {"role": "assistant", "content": "Your order ORD99999 is in transit."},
            ],
        )
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = validate_input(state)
        assert result["order_id"] == "ORD99999"

    def test_llm_extraction_for_general_query(self):
        state = make_state(current_input="show my pending orders")
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"order_id": null, "status_filter": "PENDING", "product_keyword": null, '
            '"shipping_mode": null, "carrier_filter": null, "special_query": null, '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10}'
        )
        mock_resp.usage_metadata = {"input_tokens": 100, "output_tokens": 10}

        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)

        assert result["status_filter"] == "PENDING"

    def test_llm_failure_falls_back_gracefully(self):
        state = make_state(current_input="how many orders do i have")
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.side_effect = Exception("network error")
            result = validate_input(state)
        # Should return state without crashing; order_id remains None
        assert result["order_id"] is None


# ─── validate_input_edge ─────────────────────────────────────────────────────


class TestValidateInputEdge:
    def test_response_set_routes_to_error(self):
        state = make_state(response="Guest not allowed")
        assert validate_input_edge(state) == "error_response"

    def test_no_response_routes_to_fetch(self):
        assert validate_input_edge(make_state()) == "fetch_order_data"

    def test_order_id_with_no_response_routes_to_fetch(self):
        state = make_state(order_id="ORD001", response=None)
        assert validate_input_edge(state) == "fetch_order_data"


# ─── order_found_edge ────────────────────────────────────────────────────────


class TestOrderFoundEdge:
    def test_order_data_routes_to_shipment(self):
        state = make_state(order_data={"order_id": "ORD001", "status": "DELIVERED"})
        assert order_found_edge(state) == "shipment_tracking"

    def test_response_no_order_data_routes_to_save(self):
        state = make_state(order_data=None, response="Here are your orders...")
        assert order_found_edge(state) == "save_to_db"

    def test_nothing_routes_to_error(self):
        state = make_state(order_data=None, response=None)
        assert order_found_edge(state) == "error_response"


# ─── error_response ──────────────────────────────────────────────────────────


class TestErrorResponse:
    def test_passthrough_when_response_already_set(self):
        state = make_state(response="Already set", order_id="ORD001")
        result = error_response(state)
        assert result["response"] == "Already set"

    def test_generates_error_message_when_no_response(self):
        state = make_state(order_id="ORD999")
        result = error_response(state)
        assert result["response"] is not None
        assert "ORD999" in result["response"]


# ─── _fetch_order_data_impl ──────────────────────────────────────────────────


class TestFetchOrderDataImpl:
    def _log(self):
        return MagicMock()

    def test_single_order_found(self):
        state = make_state(order_id="ORD001", user_id="test@example.com")
        row = {
            "order_id": "ORD001",
            "user_id": "test@example.com",
            "status": "DELIVERED",
            "carrier": "FedEx",
            "estimated_delivery": "2025-01-01",
        }
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchone=row)
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"]["order_id"] == "ORD001"

    def test_order_not_found_returns_error_response(self):
        state = make_state(order_id="ORD999", user_id="test@example.com")
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchone=None)
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"] is None
        assert "ORD999" in result["response"]

    def test_order_belongs_to_different_user(self):
        state = make_state(order_id="ORD001", user_id="attacker@example.com")
        row = {"order_id": "ORD001", "user_id": "owner@example.com", "status": "DELIVERED"}
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchone=row)
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"] is None
        assert result["response"] is not None

    def test_count_special_query(self):
        state = make_state(special_query="count", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.log_tool_span"):
            cur = mock_db(mock_gc, fetchone=(5,))
            result = _fetch_order_data_impl(state, self._log())
        # Should return a response message with the count
        assert result.get("response") is not None


# ─── _fetch_order_data_impl — special queries ────────────────────────────────


class TestFetchOrderDataSpecialQueries:
    def _log(self):
        return MagicMock()

    def _order_rows(self):
        return [
            {
                "order_id": "ORD001",
                "status": "DELIVERED",
                "carrier": "FedEx",
                "estimated_delivery": "2025-01-01",
                "sales_per_customer": 999,
                "items": '["Laptop"]',
                "order_date": "2024-12-01",
            },
        ]

    def test_cheapest_query(self):
        state = make_state(special_query="cheapest", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "cheapest" in result["response"].lower()
        assert result["order_data"] is None

    def test_most_expensive_query(self):
        state = make_state(special_query="most_expensive", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "expensive" in result["response"].lower()

    def test_last_week_no_orders(self):
        state = make_state(special_query="last_week", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "no orders" in result["response"].lower()

    def test_last_week_with_orders(self):
        state = make_state(special_query="last_week", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "last week" in result["response"].lower()

    def test_recent_query(self):
        state = make_state(special_query="recent", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "recent" in result["response"].lower()

    def test_oldest_query_empty(self):
        state = make_state(special_query="oldest", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "no orders" in result["response"].lower()

    def test_upcoming_query(self):
        rows = [
            {
                "order_id": "ORD002",
                "status": "IN_TRANSIT",
                "carrier": "FedEx",
                "estimated_delivery": "2025-02-01",
                "sales_per_customer": 1500,
                "items": '["Mouse"]',
                "order_date": "2024-12-20",
            }
        ]
        state = make_state(special_query="upcoming", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = _fetch_order_data_impl(state, self._log())
        assert "upcoming" in result["response"].lower() or "ORD002" in result["response"]

    def test_late_risk_query(self):
        state = make_state(special_query="late_risk", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "late" in result["response"].lower() or "risk" in result["response"].lower()


class TestFetchOrderDataFilters:
    def _log(self):
        return MagicMock()

    def test_status_filter_no_match(self):
        state = make_state(status_filter="PENDING", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"] is None

    def test_product_keyword_no_match(self):
        state = make_state(product_keyword="SSD", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "SSD" in result["response"]

    def test_carrier_filter_no_match(self):
        state = make_state(carrier_filter="FedEx", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "FedEx" in result["response"]

    def test_filter_with_results_groups_by_status(self):
        rows = [
            {
                "order_id": "ORD003",
                "status": "DELIVERED",
                "carrier": "Ekart",
                "estimated_delivery": "2025-01-10",
                "sales_per_customer": 2000,
                "items": '["Keyboard"]',
            }
        ]
        state = make_state(status_filter="DELIVERED", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=rows)
            result = _fetch_order_data_impl(state, self._log())
        assert "ORD003" in result["response"]

    def test_no_orders_at_all(self):
        state = make_state(order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"] is None


# ─── generate_response ───────────────────────────────────────────────────────


class TestGenerateResponse:
    def test_llm_invoked_and_content_stored(self):
        state = make_state(
            order_data={"order_id": "ORD001", "status": "DELIVERED"},
            tracking_info={"events": [], "current_location": "Mumbai"},
            current_input="where is my order",
        )
        mock_resp = MagicMock()
        mock_resp.content = "Your order ORD001 has been delivered."
        mock_resp.usage_metadata = {"input_tokens": 50, "output_tokens": 20}

        with patch("agents.order_agent.llm") as mock_llm:
            mock_llm.invoke.return_value = mock_resp
            result = generate_response(state)

        assert result["response"] == "Your order ORD001 has been delivered."
        assert result["total_tokens"] == 70


# ─── save_to_db ──────────────────────────────────────────────────────────────


class TestSaveToDb:
    def test_save_message_is_called(self):
        state = make_state(
            response="Your order is delivered.",
            total_tokens=100,
            total_cost_usd=0.001,
        )
        with patch("agents.order_agent.save_message") as mock_save:
            result = save_to_db(state)
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        assert call_kwargs.kwargs.get("role") == "assistant" or (call_kwargs.args and "assistant" in call_kwargs.args)


# ─── validate_input — date / special_query fixes ────────────────────────────


class TestValidateInputDateAndSpecialQuery:
    """Covers the regex fallbacks and date-priority logic added to validate_input."""

    def _run(self, msg, llm_json=None):
        from agents.order_agent import validate_input

        state = make_state(current_input=msg)
        mock_resp = MagicMock()
        mock_resp.content = llm_json or (
            '{"order_id":null,"status_filter":null,"product_keyword":null,'
            '"special_query":null,"carrier_filter":null,"shipping_mode":null,'
            '"city_filter":null,"min_price":null,"max_price":null,"limit":10}'
        )
        mock_resp.usage_metadata = {"input_tokens": 50, "output_tokens": 10}
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            return validate_input(state)

    def test_greeting_returns_intro_without_db(self):
        from agents.order_agent import validate_input

        state = make_state(current_input="hi")
        result = validate_input(state)
        assert result["response"] is not None
        assert "order" in result["response"].lower()

    def test_this_month_sets_month_and_year_filter(self):
        import datetime

        result = self._run("what are my orders this month")
        today = datetime.date.today()
        assert result["month_filter"] == today.month
        assert result["year_filter"] == today.year

    def test_last_month_sets_correct_month_year(self):
        import datetime

        result = self._run("show my orders from last month")
        today = datetime.date.today()
        first = today.replace(day=1)
        prev = first - datetime.timedelta(days=1)
        assert result["month_filter"] == prev.month
        assert result["year_filter"] == prev.year

    def test_june_2026_sets_month_6_year_2026(self):
        result = self._run("what are my orders in June 2026")
        assert result["month_filter"] == 6
        assert result["year_filter"] == 2026

    def test_jan_2026_sets_month_1_year_2026(self):
        result = self._run("show orders from jan 2026")
        assert result["month_filter"] == 1
        assert result["year_filter"] == 2026

    def test_date_filter_clears_recent_special_query(self):
        llm_json = (
            '{"order_id":null,"status_filter":null,"product_keyword":null,'
            '"special_query":"recent","carrier_filter":null,"shipping_mode":null,'
            '"city_filter":null,"min_price":null,"max_price":null,"limit":10,'
            '"month_filter":null,"year_filter":null,"date_filter":null}'
        )
        result = self._run("what are my orders in June 2026", llm_json)
        assert result["special_query"] is None
        assert result["month_filter"] == 6

    def test_this_month_clears_recent_special_query(self):
        llm_json = (
            '{"order_id":null,"status_filter":null,"product_keyword":null,'
            '"special_query":"recent","carrier_filter":null,"shipping_mode":null,'
            '"city_filter":null,"min_price":null,"max_price":null,"limit":10,'
            '"month_filter":null,"year_filter":null,"date_filter":null}'
        )
        result = self._run("what are my orders this month", llm_json)
        assert result["special_query"] is None

    def test_costliest_regex_sets_most_expensive(self):
        result = self._run("show my costliest orders")
        assert result["special_query"] == "most_expensive"

    def test_most_expensive_regex_sets_most_expensive(self):
        result = self._run("show most expensive orders")
        assert result["special_query"] == "most_expensive"

    def test_oldest_regex_sets_oldest(self):
        result = self._run("show me my oldest orders")
        assert result["special_query"] == "oldest"


class TestFetchOrderDataImplDateFilters:
    """Covers cheapest/most_expensive with month/year filters."""

    def _log(self):
        return MagicMock()

    def _order_rows(self):
        return [
            {
                "order_id": "ORD010",
                "status": "DELIVERED",
                "carrier": "FedEx",
                "estimated_delivery": "2026-06-15",
                "sales_per_customer": 1200,
                "items": '["Keyboard"]',
                "order_date": "2026-06-01",
            }
        ]

    def test_cheapest_with_month_year_filter(self):
        state = make_state(
            special_query="cheapest",
            order_id=None,
            month_filter=6,
            year_filter=2026,
        )
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "cheapest" in result["response"].lower()

    def test_most_expensive_with_year_filter(self):
        state = make_state(
            special_query="most_expensive",
            order_id=None,
            year_filter=2026,
        )
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=self._order_rows())
            result = _fetch_order_data_impl(state, self._log())
        assert "expensive" in result["response"].lower()

    def test_cheapest_no_results(self):
        state = make_state(special_query="cheapest", order_id=None, month_filter=1, year_filter=2020)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert result["response"] is not None


# ─── _fetch_order_data_impl — extra branches ────────────────────────────────


class TestFetchOrderDataImplExtra:
    def _log(self):
        return MagicMock()

    def _row(self, oid="ORD001", status="DELIVERED", carrier="FedEx"):
        return {
            "order_id": oid,
            "status": status,
            "carrier": carrier,
            "estimated_delivery": "2026-06-15",
            "sales_per_customer": 999,
            "items": '["Laptop"]',
            "order_date": "2026-05-01",
        }

    def test_upcoming_with_results(self):
        state = make_state(special_query="upcoming", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[self._row(status="IN_TRANSIT")])
            result = _fetch_order_data_impl(state, self._log())
        assert "ORD001" in result["response"] or "upcoming" in result["response"].lower()

    def test_late_risk_with_results(self):
        state = make_state(special_query="late_risk", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[self._row(status="IN_TRANSIT")])
            result = _fetch_order_data_impl(state, self._log())
        assert "ORD001" in result["response"] or "late" in result["response"].lower()

    def test_oldest_with_results(self):
        state = make_state(special_query="oldest", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[self._row()])
            result = _fetch_order_data_impl(state, self._log())
        assert "ORD001" in result["response"] or "oldest" in result["response"].lower()

    def test_last_month_empty(self):
        state = make_state(special_query="last_month", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "no orders" in result["response"].lower()

    def test_upcoming_empty(self):
        state = make_state(special_query="upcoming", order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert "no" in result["response"].lower()

    def test_filter_no_orders_at_all(self):
        state = make_state(order_id=None)
        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[])
            result = _fetch_order_data_impl(state, self._log())
        assert result["order_data"] is None

    def test_month_year_date_correction(self):
        """Date filter YYYY-MM-01 from LLM should be corrected to month+year."""
        from agents.order_agent import _execute_order_query

        with patch("agents.order_agent.get_conn") as mock_gc:
            mock_db(mock_gc, fetchall=[self._row()])
            result = _execute_order_query(
                user_id="user@test.com",
                date_filter="2026-05-01",
                month_filter=None,
                year_filter=None,
            )
        assert "orders" in result

    def test_llm_extraction_with_product_rows(self):
        """Covers the item JSON parsing loop (lines 694-703)."""
        state = make_state(current_input="where is my laptop order")
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"order_id": null, "status_filter": null, "product_keyword": "laptop", '
            '"shipping_mode": null, "carrier_filter": null, "special_query": null, '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10}'
        )
        mock_resp.usage_metadata = {"input_tokens": 100, "output_tokens": 10}

        product_rows = [('["Laptop", "Charger"]',), ('["Mouse"]',)]
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            cur = MagicMock()
            cur.fetchall.return_value = product_rows
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)
        assert result["product_keyword"] == "laptop"

    def test_llm_response_with_code_block(self):
        """Covers the code block JSON extraction branch (lines 778-783)."""
        state = make_state(current_input="show pending orders")
        json_in_block = (
            '```json\n{"order_id": null, "status_filter": "PENDING", "product_keyword": null, '
            '"shipping_mode": null, "carrier_filter": null, "special_query": null, '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10}\n```'
        )
        mock_resp = MagicMock()
        mock_resp.content = json_in_block
        mock_resp.usage_metadata = {"input_tokens": 80, "output_tokens": 20}
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)
        assert result["status_filter"] == "PENDING"

    def test_month_date_correction_may_2026(self):
        """LLM sets date_filter=2026-05-01 for 'may 2026' — should correct to month_filter=5."""
        state = make_state(current_input="show orders on may 2026")
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"order_id": null, "status_filter": null, "product_keyword": null, '
            '"shipping_mode": null, "carrier_filter": null, "special_query": null, '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10, '
            '"date_filter": "2026-05-01", "month_filter": null, "year_filter": 2026}'
        )
        mock_resp.usage_metadata = {"input_tokens": 80, "output_tokens": 20}
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)
        assert result["month_filter"] == 5
        assert result["date_filter"] is None

    def test_status_filter_with_keyword_in_message(self):
        """Status filter extracted directly from keyword in message."""
        state = make_state(current_input="show my delivered orders")
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"order_id": null, "status_filter": "DELIVERED", "product_keyword": null, '
            '"shipping_mode": null, "carrier_filter": null, "special_query": null, '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10}'
        )
        mock_resp.usage_metadata = {"input_tokens": 60, "output_tokens": 10}
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)
        assert result["status_filter"] == "DELIVERED"

    def test_special_query_count_extracted(self):
        """Covers count special query path in validate_input."""
        state = make_state(current_input="how many orders do i have in total")
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"order_id": null, "status_filter": null, "product_keyword": null, '
            '"shipping_mode": null, "carrier_filter": null, "special_query": "count", '
            '"city_filter": null, "min_price": null, "max_price": null, "limit": 10}'
        )
        mock_resp.usage_metadata = {"input_tokens": 60, "output_tokens": 10}
        with patch("agents.order_agent.get_conn") as mock_gc, patch("agents.order_agent.llm") as mock_llm:
            mock_db(mock_gc, fetchall=[])
            mock_llm.invoke.return_value = mock_resp
            result = validate_input(state)
        assert result["special_query"] == "count"
