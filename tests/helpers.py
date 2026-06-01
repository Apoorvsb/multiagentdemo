"""Shared test helpers: state factory and DB mock wiring."""

from unittest.mock import MagicMock


def make_state(**overrides) -> dict:
    base = {
        "session_id": "test-session",
        "user_id": "test@example.com",
        "request_id": "test-req-id",
        "messages": [],
        "current_input": "test input",
        "intent": None,
        "order_id": None,
        "order_data": None,
        "order_analysis": None,
        "tracking_info": None,
        "response": None,
        "error": None,
        "mlflow_run_id": None,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "conversation_summary": None,
        "search_preferences": None,
        "search_retry": 0,
        "search_results": None,
        "ranked_products": None,
        "enriched_products": None,
        "issue_type": None,
        "severity": None,
        "policy": None,
        "priority": None,
        "ticket_id": None,
        "ticket_count": 0,
        "previous_tickets": None,
        "mlflow_trace_id": None,
        "mlflow_span_id": None,
        "status_filter": None,
        "product_keyword": None,
        "carrier_filter": None,
        "shipping_mode": None,
        "special_query": None,
        "city_filter": None,
        "min_price": None,
        "max_price": None,
        "query_limit": 10,
    }
    base.update(overrides)
    return base


def mock_db(mock_get_conn, fetchone=None, fetchall=None):
    """Wire a patch('...get_conn') mock to return configured cursor results."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall if fetchall is not None else []
    conn = mock_get_conn.return_value.__enter__.return_value
    conn.cursor.return_value.__enter__.return_value = cur
    return cur
