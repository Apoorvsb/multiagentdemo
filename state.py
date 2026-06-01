from typing import TypedDict, Optional


class AgentState(TypedDict):
    session_id: str
    user_id: str
    request_id: str
    messages: list
    current_input: str
    intent: Optional[str]
    order_id: Optional[str]
    order_data: Optional[dict]
    order_analysis: Optional[str]
    tracking_info: Optional[dict]
    response: Optional[str]
    error: Optional[str]
    mlflow_run_id: Optional[str]
    total_tokens: int
    total_cost_usd: float
    search_preferences: Optional[dict]
    search_retry:       Optional[int]
    search_results:     Optional[list]
    ranked_products:    Optional[list]
    enriched_products:  Optional[list]
    issue_type:       Optional[str]
    severity:         Optional[str]
    policy:           Optional[dict]
    priority:         Optional[str]
    ticket_id:        Optional[str]
    ticket_count:     Optional[int]
    previous_tickets: Optional[list]
    response: Optional[str]
    error:    Optional[str]

    conversation_summary: Optional[str]

    # ── Observability ─────────────────────────────────────────────
    mlflow_run_id:  Optional[str]
    total_tokens:   int
    total_cost_usd: float
    mlflow_trace_id: Optional[str]
    mlflow_span_id:  Optional[str]
    status_filter:   Optional[str]
    product_keyword: Optional[str]
    carrier_filter:  Optional[str]
    shipping_mode:   Optional[str]
    special_query:   Optional[str]
    city_filter:     Optional[str]
    min_price:       Optional[float]
    max_price:       Optional[float]
    query_limit:     Optional[int]



def empty_state(session_id, user_id, request_id, messages, current_input, 
                mlflow_run_id=None, mlflow_trace_id=None, mlflow_span_id=None):
    return {
        "session_id":    session_id,
        "user_id":       user_id,
        "request_id":    request_id,
        "messages":      messages,
        "current_input": current_input,
        "intent":        None,
        "order_id":      None,
        "order_data":    None,
        "order_analysis": None,
        "tracking_info": None,
        "response":      None,
        "error":         None,
        "mlflow_run_id": mlflow_run_id,
        "total_tokens":  0,
        "total_cost_usd": 0.0,
        "conversation_summary": None,
        "search_preferences": None,
        "search_retry":       0,
        "search_results":     None,
        "ranked_products":    None,
        "enriched_products":  None,
        "issue_type":    None,
        "severity":      None,
        "policy":        None,
        "priority":      None,
        "ticket_id":     None,
        "ticket_count":  0,
        "previous_tickets": None,
        "mlflow_trace_id": mlflow_trace_id,
        "mlflow_span_id":  mlflow_span_id,
        "status_filter":   None,
        "product_keyword": None,
        "carrier_filter":  None,
        "shipping_mode":   None,
        "special_query":   None,
        "city_filter":     None,
        "min_price":       None,
        "max_price":       None,
        "query_limit":     10,
    }