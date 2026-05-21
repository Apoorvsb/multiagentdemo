import mlflow
from mlflow.entities import SpanType
from config import config

def setup_mlflow():
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)  
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
     


MODEL_PRICING = {
    "llama-3.1-8b-instant": {"input": 0.00015, "output": 0.0006},
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
    return round(
        (input_tokens  / 1000 * pricing["input"]) +
        (output_tokens / 1000 * pricing["output"]),
        6
    )


def log_llm_span(span_name, prompt_text, response_text, input_tokens, output_tokens, model, prompt_name, prompt_version):
    cost = calculate_cost(model, input_tokens, output_tokens)
    with mlflow.start_span(span_name, span_type=SpanType.LLM) as span:
        span.set_attribute("llm.model",            model)
        span.set_attribute("llm.prompt",            prompt_text)
        span.set_attribute("llm.response",          response_text)
        span.set_attribute("llm.prompt_tokens",     input_tokens)
        span.set_attribute("llm.completion_tokens", output_tokens)
        span.set_attribute("llm.cost_usd",          cost)
        span.set_attribute("prompt.name",           prompt_name)
        span.set_attribute("prompt.version",        prompt_version)
    return cost





def log_tool_span(span_name, tool_name, tool_input, tool_output):
    with mlflow.start_span(span_name, span_type=SpanType.TOOL) as span:
        span.set_attribute("tool.name",   tool_name)
        span.set_attribute("tool.input",  str(tool_input))
        span.set_attribute("tool.output", str(tool_output))


def register_prompts():
    mlflow.register_prompt(
        name="order_analysis_prompt",
        template="""You are an order status assistant.
Order data: {order_data}
Conversation history: {history}
Analyze the order status and explain it clearly to the customer.""",
        version=1,
    )
    mlflow.register_prompt(
        name="order_analysis_prompt",
        template="""You are a helpful order status assistant.
Order details: {order_data}
Previous conversation: {history}
Analyze the order. Include:
1. Current status in plain English
2. Expected delivery date
3. Any delays or issues
4. What the customer should do next""",
        version=2,
    )
    mlflow.register_prompt(
        name="response_generation_prompt",
        template="""You are a helpful customer service assistant.
Order analysis: {order_analysis}
Tracking info: {tracking_info}
Customer asked: {question}
Write a clear friendly response in 3-4 sentences.""",
        version=1,
    )
    print("Prompts registered successfully.")