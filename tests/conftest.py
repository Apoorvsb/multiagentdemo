"""
Pytest configuration: mock heavy external dependencies BEFORE any app module
imports, so ChatGroq, mlflow, opentelemetry and prometheus_client are never
instantiated against real services during tests.
"""

import sys
import os
from unittest.mock import MagicMock

# ─── sys.path ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (ROOT, TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ─── langchain_groq ──────────────────────────────────────────────────────────
# Prevents API-key validation at import time when each agent builds its LLM.
sys.modules["langchain_groq"] = MagicMock()

# ─── mlflow ──────────────────────────────────────────────────────────────────
_mock_mlflow = MagicMock()
sys.modules["mlflow"] = _mock_mlflow
sys.modules["mlflow.tracking"] = MagicMock()
sys.modules["mlflow.entities"] = MagicMock()
sys.modules["mlflow.genai"] = MagicMock()

# ─── opentelemetry ───────────────────────────────────────────────────────────
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.propagate"] = MagicMock()
sys.modules["opentelemetry.context"] = MagicMock()

# ─── prometheus_client ───────────────────────────────────────────────────────
sys.modules["prometheus_client"] = MagicMock()

# ─── Shared helpers ──────────────────────────────────────────────────────────
import pytest
from helpers import make_state


@pytest.fixture
def base_state():
    return make_state()
