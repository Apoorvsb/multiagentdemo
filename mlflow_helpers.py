import mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import SpanType
from config import config


_client = MlflowClient()


def setup_mlflow():
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)



MODEL_PRICING = {
    "llama-3.1-8b-instant": {"input": 0.00015, "output": 0.0006},
    "gemini-2.0-flash":     {"input": 0.00015, "output": 0.0006},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
    return round(
        (input_tokens  / 1000 * pricing["input"]) +
        (output_tokens / 1000 * pricing["output"]),
        6
    )


def get_active_trace_id() -> str | None:
    try:
        span = mlflow.get_current_active_span()
        if span:
            return span.trace_id
        return None
    except Exception:
        return None


def get_active_span_id() -> str | None:
    try:
        span = mlflow.get_current_active_span()
        if span:
            return span.span_id
        return None
    except Exception:
        return None


def log_llm_span(span_name, prompt_text, response_text,
                 input_tokens, output_tokens, model,
                 prompt_name, prompt_version,
                 trace_id=None, parent_id=None):
    cost = calculate_cost(model, input_tokens, output_tokens)
    print(f"[DEBUG] log_llm_span called: {span_name}")

    try:
        with mlflow.start_span(
            name      = span_name,
            span_type = "LLM",
        ) as span:
            span.set_inputs({"prompt": prompt_text[:500]})
            span.set_outputs({"response": response_text[:500]})
            span.set_attribute("model",          model)
            span.set_attribute("prompt_name",    prompt_name)
            span.set_attribute("prompt_version", str(prompt_version))
            span.set_attribute("input_tokens",   input_tokens)
            span.set_attribute("output_tokens",  output_tokens)
            span.set_attribute("total_tokens",   input_tokens + output_tokens)
            span.set_attribute("cost_usd",       cost)
        print(f"[DEBUG] span created: {span_name}")
    except Exception as e:
        print(f"  [mlflow] log_llm_span error ({span_name}): {e}")

    return cost


def log_tool_span(span_name, tool_name, tool_input, tool_output,
                  trace_id=None, parent_id=None):
    print(f"[DEBUG] log_tool_span called: {span_name}")
    try:
        with mlflow.start_span(
            name      = span_name,
            span_type = "TOOL",
        ) as span:
            span.set_inputs({"tool_input": str(tool_input)[:500]})
            span.set_outputs({"tool_output": str(tool_output)[:500]})
            span.set_attribute("tool_name", tool_name)
        print(f"[DEBUG] span created: {span_name}")
    except Exception as e:
        print(f"  [mlflow] log_tool_span error ({span_name}): {e}")

def register_prompts():
    try:
        mlflow.genai.register_prompt(
            name     = "order_analysis_prompt",
            template = """You are an order status assistant.
Order data: {{order_data}}
Conversation history: {{history}}

Analyze the order and include ALL of the following:
1. Customer name from the order data
2. Current status in plain English
3. Carrier name and tracking number
4. Expected delivery date
5. Any delays or issues
6. What the customer should expect next

Always mention the customer name and tracking number in your response.""",
        )
        print("Registered: order_analysis_prompt")
    except Exception as e:
        print(f"order_analysis_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "response_generation_prompt",
            template = """You are a helpful customer service assistant.
Order analysis: {{order_analysis}}
Tracking info: {{tracking_info}}
Customer asked: {{question}}

Write a clear friendly response in 3-4 sentences.
Always include customer name, current status, carrier name, tracking number and ETA.""",
        )
        print("Registered: response_generation_prompt")
    except Exception as e:
        print(f"response_generation_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "product_ranking_prompt",
            template = """You are a product recommendation assistant.

User request: {{user_request}}

Available products:
{{products_text}}

Rank these products from best to worst match for the user request.
Return ONLY a comma-separated list of product numbers in order of recommendation.
Example: 3,1,5,2,4""",
        )
        print("Registered: product_ranking_prompt")
    except Exception as e:
        print(f"product_ranking_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "format_recommendations_prompt",
            template = """You are a helpful product recommendation assistant.

User asked: {{user_request}}

Top recommendations:
{{products_text}}

Write a friendly 4-5 sentence response recommending these products.
Mention the price, rating, and key benefits of each.""",
        )
        print("Registered: format_recommendations_prompt")
    except Exception as e:
        print(f"format_recommendations_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "classify_issue_prompt",
            template = """You are a customer support classifier.

Classify the customer complaint into exactly one issue type:
- damaged_goods
- wrong_item
- missing_item
- refund_request
- technical_issue
- billing_inquiry
- cancellation_request
- delayed_delivery
- warranty_claim
- return_request
- general_complaint

Customer message: {{customer_message}}
Conversation history: {{history}}

Return only the issue type label. Nothing else.""",
        )
        print("Registered: classify_issue_prompt")
    except Exception as e:
        print(f"classify_issue_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "draft_resolution_prompt",
            template = """You are a helpful customer support agent.

Customer complaint: {{customer_message}}
Issue type: {{issue_type}}
Severity: {{severity}}
Company policy: {{policy_text}}
Ticket ID: {{ticket_id}}

Write a clear empathetic resolution message.
Include acknowledgement, action based on policy, expected timeline, and ticket ID if created.
Keep it under 5 sentences.""",
        )
        print("Registered: draft_resolution_prompt")
    except Exception as e:
        print(f"draft_resolution_prompt: {e}")

    try:
        mlflow.genai.register_prompt(
            name     = "escalation_response_prompt",
            template = """You are a helpful customer support agent.

Customer complaint: {{customer_message}}
Issue type: {{issue_type}}
Severity: HIGH
Priority: {{priority}}
Ticket ID: {{ticket_id}}
SLA: {{sla}}
Policy: {{policy_text}}

Write an empathetic escalation response.
Mention the ticket ID, priority, and when they can expect resolution.
Keep it under 5 sentences.""",
        )
        print("Registered: escalation_response_prompt")
    except Exception as e:
        print(f"escalation_response_prompt: {e}")

    print("\nAll prompts registered.")