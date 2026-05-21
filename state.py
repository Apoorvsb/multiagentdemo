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


def empty_state(session_id, user_id, request_id, messages, current_input, mlflow_run_id=None):
    return {
        "session_id": session_id,
        "user_id": user_id,
        "request_id": request_id,
        "messages": messages,
        "current_input": current_input,
        "intent": None,
        "order_id": None,
        "order_data": None,
        "order_analysis": None,
        "tracking_info": None,
        "response": None,
        "error": None,
        "mlflow_run_id": mlflow_run_id,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
    }