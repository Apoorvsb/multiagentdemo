import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    LLM_MODEL = os.getenv(
        "LLM_MODEL",
        "llama-3.1-8b-instant"
    )

    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "multiagent")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")

    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "multi-agent-app")
    

    ORDER_ANALYSIS_PROMPT_VERSION = int(os.getenv("ORDER_ANALYSIS_PROMPT_VERSION", "1"))
    RESPONSE_GENERATION_PROMPT_VERSION = int(os.getenv("RESPONSE_GENERATION_PROMPT_VERSION", "1"))

    SESSION_EXPIRY_MINUTES = int(os.getenv("SESSION_EXPIRY_MINUTES", "30"))

    LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki/api/v1/push")
    PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "8001"))

    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))


config = Config()