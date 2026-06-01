"""Unit tests for FastAPI endpoints in main.py."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan side-effects (setup_mlflow, create_tables) mocked out."""
    with patch("main.setup_mlflow"), \
         patch("main.create_tables"), \
         patch("database.get_conn") as mock_gc:
        # Provide a valid-enough cursor so create_tables doesn't explode.
        cur = MagicMock()
        conn = mock_gc.return_value.__enter__.return_value
        conn.cursor.return_value.__enter__.return_value = cur
        from main import app
        with TestClient(app) as c:
            yield c


# ─── /health ─────────────────────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─── /register ───────────────────────────────────────────────────────────────

class TestRegister:
    def test_new_user_registration(self, client):
        with patch("main.user_exists", return_value=False), \
             patch("main.get_or_create_user"), \
             patch("main.update_user_metadata"), \
             patch("main.get_or_create_session", return_value="sess-123"):
            resp = client.post("/register", json={"name": "Alice", "email": "alice@example.com"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "alice@example.com"
        assert data["existing_user"] is False

    def test_existing_user_login_on_register(self, client):
        with patch("main.user_exists", return_value=True), \
             patch("main.get_or_create_session", return_value="sess-existing"):
            resp = client.post("/register", json={"name": "Alice", "email": "alice@example.com"})

        assert resp.status_code == 200
        assert resp.json()["existing_user"] is True


# ─── /login ──────────────────────────────────────────────────────────────────

class TestLogin:
    def test_valid_user_login(self, client):
        with patch("main.user_exists", return_value=True), \
             patch("main.get_or_create_session", return_value="sess-abc"), \
             patch("main.get_conn") as mock_gc:
            cur = MagicMock()
            cur.fetchall.return_value = []
            conn = mock_gc.return_value.__enter__.return_value
            conn.cursor.return_value.__enter__.return_value = cur
            resp = client.post("/login", json={"user_id": "alice@example.com"})

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-abc"

    def test_unknown_user_returns_404(self, client):
        with patch("main.user_exists", return_value=False):
            resp = client.post("/login", json={"user_id": "nobody@example.com"})

        assert resp.status_code == 404


# ─── /chat ───────────────────────────────────────────────────────────────────

class TestChat:
    def test_no_session_header_returns_401(self, client):
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 401

    def test_invalid_session_returns_401(self, client):
        with patch("main.get_session_row", return_value=None):
            resp = client.post(
                "/chat",
                json={"message": "hello"},
                headers={"X-Session-ID": "bad-session"},
            )
        assert resp.status_code == 401

    def test_valid_chat_returns_response(self, client):
        session_row = {"session_id": "sess-ok", "user_id": "test@example.com"}
        pipeline_result = {
            "response":       "Your order ORD001 is on the way.",
            "intent":         "order_query",
            "total_tokens":   50,
            "total_cost_usd": 0.0001,
        }

        with patch("main.get_session_row", return_value=session_row), \
             patch("main.get_or_create_session", return_value="sess-ok"), \
             patch("main.load_conversation_history", return_value=[]), \
             patch("main.save_message"), \
             patch("main.update_session_agent"), \
             patch("main.pipeline") as mock_pipe, \
             patch("main.mlflow") as mock_mf:

            # Configure mlflow context managers
            mock_run = MagicMock()
            mock_run.info.run_id = "run-001"
            mock_mf.start_run.return_value.__enter__.return_value = mock_run
            mock_mf.start_run.return_value.__exit__.return_value = False
            mock_span = MagicMock()
            mock_span.trace_id = "trace-001"
            mock_span.span_id  = "span-001"
            mock_mf.start_span.return_value.__enter__.return_value = mock_span
            mock_mf.start_span.return_value.__exit__.return_value = False

            mock_pipe.invoke.return_value = pipeline_result

            resp = client.post(
                "/chat",
                json={"message": "where is my order"},
                headers={"X-Session-ID": "sess-ok"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "order_query"
        assert "ORD001" in data["response"]

    def test_expired_session_returns_400(self, client):
        session_row = {"session_id": "sess-exp", "user_id": "test@example.com"}
        with patch("main.get_session_row", return_value=session_row), \
             patch("main.get_or_create_session", side_effect=ValueError("Session expired")):
            resp = client.post(
                "/chat",
                json={"message": "hello"},
                headers={"X-Session-ID": "sess-exp"},
            )
        assert resp.status_code == 400
