import uuid
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


def classify_issue(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "classify_issue")
    log.info("LLM called")

    prompt_template = mlflow.genai.load_prompt("prompts:/classify_issue_prompt/1")
    prompt = prompt_template.format(
        customer_message = state['current_input'],
        history          = str(state['messages']),
    )

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        issue_type    = response.content.strip().lower().replace(" ", "_")
    except Exception as e:
        log.error(f"Classification failed: {e}")
        issue_type    = "general_complaint"
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0
        response      = type("R", (), {"content": issue_type})()

    log_llm_span(
        span_name      = "classify_issue",
        prompt_text    = prompt,
        response_text  = issue_type,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "classify_issue_prompt",
        prompt_version = 1,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

    log.info(f"Issue classified: {issue_type}")
    return {
        **state,
        "issue_type":     issue_type,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def assess_severity(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "assess_severity")
    log.info("Node entered")

    issue_type = state.get("issue_type", "general_complaint")

    high_severity_issues = [
        "damaged_goods", "missing_item", "wrong_item",
        "warranty_claim", "account_issue", "product_not_as_described",
    ]
    medium_severity_issues = [
        "refund_request", "technical_issue", "billing_inquiry",
        "delayed_delivery", "payment_failed",
    ]

    if issue_type in high_severity_issues:
        severity = "HIGH"
    elif issue_type in medium_severity_issues:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    log_tool_span(
        span_name  = "assess_severity",
        tool_name  = "severity_rules_engine",
        tool_input = {"issue_type": issue_type},
        tool_output = {"severity": severity},
        trace_id   = state.get("mlflow_trace_id"),
        parent_id  = state.get("mlflow_span_id"),
    )

    log.info(f"Severity assessed: {severity}")
    return {**state, "severity": severity}


def severity_edge(state: AgentState) -> str:
    if state.get("severity") == "HIGH":
        return "escalation_handler"
    return "lookup_policy"


def lookup_policy(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "lookup_policy")
    log.info("Tool called: lookup_policy")

    issue_type = state.get("issue_type", "general_complaint")
    policy     = None

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM policies WHERE issue_type = %s",
                    [issue_type]
                )
                row = cur.fetchone()
                if row:
                    policy = dict(row)
                else:
                    cur.execute(
                        "SELECT * FROM policies WHERE issue_type = 'general_complaint'"
                    )
                    row = cur.fetchone()
                    if row:
                        policy = dict(row)
    except Exception as e:
        log.error(f"Policy lookup error: {e}")

    log_tool_span(
        span_name   = "lookup_policy",
        tool_name   = "postgresql_policies_table",
        tool_input  = {"issue_type": issue_type},
        tool_output = {"found": bool(policy), "policy": str(policy)},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
    )

    log.info(f"Policy found: {bool(policy)}")
    return {**state, "policy": policy}


# ── Escalation subgraph nodes ─────────────────────────────

def check_history(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "check_history")
    log.info("Checking complaint history")

    user_id          = state.get("user_id")
    previous_tickets = []
    ticket_count     = 0

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT ticket_id, issue_type, priority, status, created_at
                       FROM tickets WHERE user_id = %s
                       ORDER BY created_at DESC LIMIT 5""",
                    [user_id]
                )
                rows             = cur.fetchall()
                previous_tickets = [dict(r) for r in rows]
                ticket_count     = len(previous_tickets)
    except Exception as e:
        log.error(f"History check error: {e}")

    log_tool_span(
        span_name   = "check_history",
        tool_name   = "postgresql_tickets_table",
        tool_input  = {"user_id": user_id},
        tool_output = {"ticket_count": ticket_count},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
    )

    log.info(f"Found {ticket_count} previous tickets")
    return {**state, "previous_tickets": previous_tickets, "ticket_count": ticket_count}


def assign_priority(state: AgentState) -> AgentState:
    log          = get_log(state["request_id"], "support_agent", "assign_priority")
    ticket_count = state.get("ticket_count", 0)
    severity     = state.get("severity", "LOW")

    if severity == "HIGH" and ticket_count >= 2:
        priority = "PRIORITY_1"
    elif severity == "HIGH":
        priority = "PRIORITY_2"
    elif severity == "MEDIUM" and ticket_count >= 2:
        priority = "PRIORITY_2"
    elif severity == "MEDIUM":
        priority = "PRIORITY_3"
    else:
        priority = "PRIORITY_4"

    log_tool_span(
        span_name   = "assign_priority",
        tool_name   = "priority_rules_engine",
        tool_input  = {"severity": severity, "ticket_count": ticket_count},
        tool_output = {"priority": priority},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
    )

    log.info(f"Priority assigned: {priority}")
    return {**state, "priority": priority}


def create_ticket(state: AgentState) -> AgentState:
    log       = get_log(state["request_id"], "support_agent", "create_ticket")
    log.info("Tool called: create_ticket")
    ticket_id = f"TKT{str(uuid.uuid4())[:8].upper()}"

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tickets
                       (ticket_id, user_id, session_id, issue_type,
                        severity, priority, status, description)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        ticket_id,
                        state.get("user_id"),
                        state.get("session_id"),
                        state.get("issue_type"),
                        state.get("severity"),
                        state.get("priority"),
                        "Open",
                        state["current_input"][:500],
                    ]
                )
        log.info(f"Ticket created: {ticket_id}")
    except Exception as e:
        log.error(f"Ticket creation error: {e}")
        ticket_id = "TKT_ERROR"

    log_tool_span(
        span_name   = "create_ticket",
        tool_name   = "postgresql_tickets_table",
        tool_input  = {"issue_type": state.get("issue_type"), "priority": state.get("priority")},
        tool_output = {"ticket_id": ticket_id},
        trace_id    = state.get("mlflow_trace_id"),
        parent_id   = state.get("mlflow_span_id"),
    )

    return {**state, "ticket_id": ticket_id}


def build_escalation_subgraph():
    sub = StateGraph(AgentState)
    sub.add_node("check_history",   check_history)
    sub.add_node("assign_priority", assign_priority)
    sub.add_node("create_ticket",   create_ticket)
    sub.set_entry_point("check_history")
    sub.add_edge("check_history",   "assign_priority")
    sub.add_edge("assign_priority", "create_ticket")
    sub.add_edge("create_ticket",   END)
    return sub.compile()


def draft_resolution(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "draft_resolution")
    log.info("LLM called")

    policy      = state.get("policy", {})
    ticket_id   = state.get("ticket_id")
    prompt_template = mlflow.genai.load_prompt("prompts:/draft_resolution_prompt/1")
    from datetime import datetime, timezone, timedelta

    prompt = prompt_template.format(
    customer_message = state['current_input'],
    issue_type       = state.get('issue_type', ''),
    severity         = state.get('severity', 'LOW'),
    policy_text      = policy.get('policy_text', '') if policy else '',
    ticket_id        = str(ticket_id or 'N/A'),
    current_date     = datetime.now().strftime('%B %d, %Y'),
)

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        resolution    = response.content
    except Exception as e:
        log.error(f"Draft resolution failed: {e}")
        resolution    = f"We have received your complaint and will resolve it within 24 hours.{f' Ticket: {ticket_id}.' if ticket_id else ''}"
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0

    log_llm_span(
        span_name      = "draft_resolution",
        prompt_text    = prompt,
        response_text  = resolution,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "draft_resolution_prompt",
        prompt_version = 1,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

    log.info("Resolution drafted")
    return {
        **state,
        "response":       resolution,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def generate_escalation_response(state: AgentState) -> AgentState:
    log       = get_log(state["request_id"], "support_agent", "generate_escalation_response")
    log.info("LLM called")

    ticket_id   = state.get("ticket_id", "N/A")
    priority    = state.get("priority",  "PRIORITY_3")
    policy      = state.get("policy",    {})
    priority_sla = {
        "PRIORITY_1": "2 hours",
        "PRIORITY_2": "4 hours",
        "PRIORITY_3": "24 hours",
        "PRIORITY_4": "48 hours",
    }
    sla = priority_sla.get(priority, "24 hours")

    prompt_template = mlflow.genai.load_prompt("prompts:/escalation_response_prompt/1")
    prompt = prompt_template.format(
        customer_message = state['current_input'],
        issue_type       = state.get('issue_type', ''),
        priority         = priority,
        ticket_id        = str(ticket_id),
        sla              = sla,
        policy_text      = policy.get('policy_text', '') if policy else '',
    )

    try:
        response      = llm.invoke(prompt)
        usage         = response.usage_metadata
        input_tokens  = usage.get("input_tokens",  0)
        output_tokens = usage.get("output_tokens", 0)
        cost          = calculate_cost(config.LLM_MODEL, input_tokens, output_tokens)
        resolution    = response.content
    except Exception as e:
        log.error(f"Escalation response failed: {e}")
        resolution    = f"Your complaint has been escalated with ticket ID {ticket_id}. Our team will contact you within {sla}."
        cost          = 0.0
        input_tokens  = 0
        output_tokens = 0

    log_llm_span(
        span_name      = "generate_escalation_response",
        prompt_text    = prompt,
        response_text  = resolution,
        input_tokens   = input_tokens,
        output_tokens  = output_tokens,
        model          = config.LLM_MODEL,
        prompt_name    = "escalation_response_prompt",
        prompt_version = 1,
        trace_id       = state.get("mlflow_trace_id"),
        parent_id      = state.get("mlflow_span_id"),
    )

    log.info("Escalation response generated")
    return {
        **state,
        "response":       resolution,
        "total_tokens":   state["total_tokens"]   + input_tokens + output_tokens,
        "total_cost_usd": state["total_cost_usd"] + cost,
    }


def save_to_db(state: AgentState) -> AgentState:
    log = get_log(state["request_id"], "support_agent", "save_to_db")
    log.info("Saving response to DB")
    save_message(
        session_id    = state["session_id"],
        role          = "assistant",
        content       = state["response"],
        agent_name    = "support_agent",
        token_usage   = {
            "total_tokens":   state["total_tokens"],
            "total_cost_usd": state["total_cost_usd"],
        },
        mlflow_run_id = state.get("mlflow_run_id"),
    )
    log.info("Response saved")
    return state


def build_support_agent():
    graph = StateGraph(AgentState)

    graph.add_node("classify_issue",               classify_issue)
    graph.add_node("assess_severity",              assess_severity)
    graph.add_node("lookup_policy",                lookup_policy)
    graph.add_node("escalation_handler",           build_escalation_subgraph())
    graph.add_node("draft_resolution",             draft_resolution)
    graph.add_node("generate_escalation_response", generate_escalation_response)
    graph.add_node("save_to_db",                   save_to_db)

    graph.set_entry_point("classify_issue")
    graph.add_edge("classify_issue", "assess_severity")

    graph.add_conditional_edges("assess_severity", severity_edge, {
        "escalation_handler": "escalation_handler",
        "lookup_policy":      "lookup_policy",
    })

    graph.add_edge("lookup_policy",                "draft_resolution")
    graph.add_edge("escalation_handler",           "lookup_policy")
    graph.add_edge("draft_resolution",             "save_to_db")
    graph.add_edge("generate_escalation_response", "save_to_db")
    graph.add_edge("save_to_db",                   END)

    return graph.compile()


support_agent = build_support_agent()


if __name__ == "__main__":
    from state import empty_state
    from database import get_or_create_user, get_or_create_session

    get_or_create_user("test-user")
    session_id = get_or_create_session(None, "test-user")

    test_cases = [
        "my laptop arrived with a cracked screen",
        "I want to cancel my order",
        "I was charged twice for the same order",
    ]

    for msg in test_cases:
        print(f"\n--- Testing: '{msg}' ---")
        state = empty_state(
            session_id    = session_id,
            user_id       = "test-user",
            request_id    = "test-req-003",
            messages      = [],
            current_input = msg,
        )
        result = support_agent.invoke(state)
        print(f"Issue:    {result.get('issue_type')}")
        print(f"Severity: {result.get('severity')}")
        print(f"Ticket:   {result.get('ticket_id')}")
        print(f"Response: {result['response'][:100]}...")