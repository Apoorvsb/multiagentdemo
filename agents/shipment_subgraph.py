import psycopg2.extras
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mlflow
from langgraph.graph import StateGraph, END
from state import AgentState
from logger import get_log
from database import get_conn


# ─────────────────────────────────────────────
# MOCK CARRIER API LAYER
# Simulates a real HTTP call to carrier APIs
# but retrieves data from PostgreSQL instead
# ─────────────────────────────────────────────

def mock_carrier_api_call(carrier: str, tracking_number: str) -> dict:
    """
    Simulates hitting a real carrier API endpoint.
    In production replace this with a real httpx.get() call.
    For now it queries the tracking_events table in PostgreSQL.
    """
    print(f"[MOCK API] POST https://api.{carrier.lower()}.com/track/v1/shipments")
    print(f"[MOCK API] Payload: {{'tracking_number': '{tracking_number}'}}")
    print(f"[MOCK API] Authorization: Bearer fake-{carrier.lower()}-api-key")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM tracking_events WHERE tracking_number = %s",
                [tracking_number]
            )
            row = cur.fetchone()

    if row:
        data = dict(row)
        print(f"[MOCK API] Response 200 OK — tracking data found")
        return {
            "status_code":        200,
            "tracking_number":    data["tracking_number"],
            "carrier":            data["carrier"],
            "current_location":   data["current_location"],
            "status":             data["status"],
            "last_update":        data["last_update"],
            "estimated_delivery": data["estimated_delivery"],
            "events":             data["events"],
        }
    else:
        print(f"[MOCK API] Response 404 — tracking number not found")
        return {
            "status_code":     404,
            "tracking_number": tracking_number,
            "error":           "Tracking number not found",
        }


# ─────────────────────────────────────────────
# SUBGRAPH NODES
# ─────────────────────────────────────────────
@mlflow.trace(name="get_carrier_info", span_type="TOOL")
def get_carrier_info(state: AgentState) -> AgentState:
    order_data = state.get("order_data") or {}
    tracking_info = {
        "carrier":         order_data.get("carrier", "FedEx"),
        "tracking_number": order_data.get("tracking_number", ""),
    }
    return {**state, "tracking_info": tracking_info}



@mlflow.trace(name="fetch_tracking", span_type="TOOL")
def fetch_tracking(state: AgentState) -> AgentState:
    tracking_info = state.get("tracking_info") or {}
    carrier        = tracking_info.get("carrier", "FedEx")
    tracking_number = tracking_info.get("tracking_number", "")

    log = get_log(state["request_id"], "order_agent", "fetch_tracking")
    log.info(f"Calling mock carrier API | carrier={carrier} | tracking={tracking_number}")

    # This looks like a real API call — but hits the DB behind the scenes
    api_response = mock_carrier_api_call(carrier, tracking_number)

    if api_response.get("status_code") == 200:
        log.info("Mock API returned 200 OK")
        return {
            **state,
            "tracking_info": {
                **tracking_info,
                "current_location":   api_response.get("current_location"),
                "status":             api_response.get("status"),
                "last_update":        api_response.get("last_update"),
                "estimated_delivery": api_response.get("estimated_delivery"),
                "events":             api_response.get("events"),
            }
        }
    else:
        log.warning("Mock API returned 404 — tracking not found")
        return {
            **state,
            "tracking_info": {
                **tracking_info,
                "current_location":   "Unknown",
                "status":             "NOT_FOUND",
                "estimated_delivery": "N/A",
                "events":             [],
            }
        }


@mlflow.trace(name="parse_eta", span_type="CHAIN")
def parse_eta(state: AgentState) -> AgentState:
    tracking_info   = state.get("tracking_info") or {}
    raw_eta         = tracking_info.get("estimated_delivery", "")

    if "T14" in raw_eta:
        formatted_eta = "Today by 2:00 PM"
    elif "T18" in raw_eta:
        formatted_eta = "Today by 6:00 PM"
    elif raw_eta and "T" not in raw_eta:
        formatted_eta = f"By {raw_eta}"
    else:
        formatted_eta = "Estimated delivery date not available"

    return {
        **state,
        "tracking_info": {
            **tracking_info,
            "formatted_eta": formatted_eta,
        }
    }


# ─────────────────────────────────────────────
# BUILD SUBGRAPH
# ─────────────────────────────────────────────

def build_shipment_subgraph():
    graph = StateGraph(AgentState)

    graph.add_node("get_carrier_info", get_carrier_info)
    graph.add_node("fetch_tracking",   fetch_tracking)
    graph.add_node("parse_eta",        parse_eta)

    graph.set_entry_point("get_carrier_info")
    graph.add_edge("get_carrier_info", "fetch_tracking")
    graph.add_edge("fetch_tracking",   "parse_eta")
    graph.add_edge("parse_eta",        END)

    return graph.compile()