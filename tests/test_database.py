"""Unit tests for database.py — all psycopg2 calls are mocked."""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta


def _make_conn_mock(fetchone=None, fetchall=None):
    """Return (mock_connect, mock_cur) wired up for context-manager usage."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall if fetchall is not None else []

    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = MagicMock(
        __enter__=MagicMock(return_value=cur),
        __exit__=MagicMock(return_value=False),
    )

    mock_connect = MagicMock(return_value=conn)
    return mock_connect, cur


# ─── get_or_create_user ──────────────────────────────────────────────────────

class TestGetOrCreateUser:
    def test_creates_new_user_when_not_found(self):
        mock_connect, cur = _make_conn_mock(fetchone=None)
        with patch("database.psycopg2.connect", mock_connect):
            from database import get_or_create_user
            get_or_create_user("newuser@example.com")

        execute_calls = [str(c) for c in cur.execute.call_args_list]
        insert_called = any("INSERT" in c for c in execute_calls)
        assert insert_called, "INSERT should be called for a new user"

    def test_skips_insert_when_user_exists(self):
        mock_connect, cur = _make_conn_mock(fetchone=("newuser@example.com",))
        with patch("database.psycopg2.connect", mock_connect):
            from database import get_or_create_user
            get_or_create_user("existing@example.com")

        execute_calls = [str(c) for c in cur.execute.call_args_list]
        insert_called = any("INSERT" in c for c in execute_calls)
        assert not insert_called, "INSERT should NOT be called when user already exists"


# ─── get_or_create_session ───────────────────────────────────────────────────

class TestGetOrCreateSession:
    def test_creates_new_session_when_none_provided_and_none_active(self):
        mock_connect, cur = _make_conn_mock(fetchone=None)
        with patch("database.psycopg2.connect", mock_connect), \
             patch("database.uuid.uuid4", return_value=MagicMock(hex="abc123", __str__=lambda s: "abc123")):
            from database import get_or_create_session
            sess_id = get_or_create_session(None, "user@example.com")

        # INSERT should be called for the new session
        execute_calls = [str(c) for c in cur.execute.call_args_list]
        assert any("INSERT" in c for c in execute_calls)

    def test_reuses_existing_active_session(self):
        existing = {"session_id": "sess-active"}
        mock_connect, cur = _make_conn_mock(fetchone=existing)
        with patch("database.psycopg2.connect", mock_connect):
            from database import get_or_create_session
            sess_id = get_or_create_session(None, "user@example.com")

        assert sess_id == "sess-active"

    def test_raises_value_error_for_expired_session(self):
        expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_session = {
            "session_id":     "sess-old",
            "last_active_at": expired_time,
            "user_id":        "user@example.com",
        }
        mock_connect, cur = _make_conn_mock(fetchone=expired_session)

        with patch("database.psycopg2.connect", mock_connect), \
             patch("database.config.SESSION_EXPIRY_MINUTES", 30):
            from database import get_or_create_session
            with pytest.raises(ValueError, match="expired"):
                get_or_create_session("sess-old", "user@example.com")

    def test_returns_session_id_for_valid_existing_session(self):
        valid_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        valid_session = {
            "session_id":     "sess-valid",
            "last_active_at": valid_time,
            "user_id":        "user@example.com",
        }
        mock_connect, cur = _make_conn_mock(fetchone=valid_session)

        with patch("database.psycopg2.connect", mock_connect), \
             patch("database.config.SESSION_EXPIRY_MINUTES", 30):
            from database import get_or_create_session
            sess_id = get_or_create_session("sess-valid", "user@example.com")

        assert sess_id == "sess-valid"


# ─── load_conversation_history ───────────────────────────────────────────────

class TestLoadConversationHistory:
    def test_returns_list_of_role_content_dicts(self):
        rows = [
            {"role": "user",      "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        mock_connect, cur = _make_conn_mock(fetchall=rows)
        with patch("database.psycopg2.connect", mock_connect):
            from database import load_conversation_history
            history = load_conversation_history("sess-123")

        assert history == [
            {"role": "user",      "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def test_returns_empty_list_for_new_session(self):
        mock_connect, cur = _make_conn_mock(fetchall=[])
        with patch("database.psycopg2.connect", mock_connect):
            from database import load_conversation_history
            history = load_conversation_history("sess-new")

        assert history == []


# ─── save_message ────────────────────────────────────────────────────────────

class TestSaveMessage:
    def test_inserts_message_row(self):
        mock_connect, cur = _make_conn_mock()
        with patch("database.psycopg2.connect", mock_connect):
            from database import save_message
            save_message(
                session_id="sess-123",
                role="user",
                content="hello world",
            )

        execute_calls = [str(c) for c in cur.execute.call_args_list]
        assert any("INSERT" in c for c in execute_calls)

    def test_inserts_assistant_message_with_agent_name(self):
        mock_connect, cur = _make_conn_mock()
        with patch("database.psycopg2.connect", mock_connect):
            from database import save_message
            save_message(
                session_id="sess-123",
                role="assistant",
                content="Your order is delivered.",
                agent_name="order_agent",
                token_usage={"total_tokens": 42},
            )

        execute_calls = [str(c) for c in cur.execute.call_args_list]
        assert any("INSERT" in c for c in execute_calls)


# ─── update_session_agent ────────────────────────────────────────────────────

class TestUpdateSessionAgent:
    def test_update_called_with_correct_session(self):
        mock_connect, cur = _make_conn_mock()
        with patch("database.psycopg2.connect", mock_connect):
            from database import update_session_agent
            update_session_agent("sess-123", "order_agent")

        execute_calls = [str(c) for c in cur.execute.call_args_list]
        assert any("UPDATE" in c for c in execute_calls)
