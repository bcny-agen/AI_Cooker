"""Persistence lifecycle tests for the Python-owned summary table."""

from __future__ import annotations

import unittest
from contextlib import AbstractContextManager
from datetime import datetime
from unittest.mock import patch

from app.config.settings import Settings
from app.memory.conversation_summary import (
    ConversationSummary,
    MySQLConversationSummaryStore,
)


class FakeCursor(AbstractContextManager):
    def __init__(self, rows: dict[str, tuple]) -> None:
        self.rows = rows
        self.result = None

    def execute(self, sql: str, params=None) -> None:
        normalized = " ".join(sql.split()).upper()
        if normalized.startswith("CREATE TABLE"):
            return
        if normalized.startswith("INSERT INTO"):
            assert params is not None
            conversation_id = params[0]
            self.rows[conversation_id] = (
                params[1], params[2], params[3], params[4], params[5],
                datetime(2026, 1, 1),
            )
            return
        if normalized.startswith("SELECT"):
            assert params is not None
            self.result = self.rows.get(params[0])
            return
        if normalized.startswith("DELETE FROM"):
            assert params is not None
            self.rows.pop(params[0], None)
            return
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self.result

    def __exit__(self, *_args) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: dict[str, tuple]) -> None:
        self.rows = rows
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.rows)

    def ping(self, reconnect: bool) -> None:
        assert reconnect

    def close(self) -> None:
        self.closed = True


def settings() -> Settings:
    return Settings(
        model_name="step-3.7-flash",
        model_api_key="key",
        model_base_url="https://model.example/v1",
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="cooker",
        mysql_password="password",
        mysql_database="agent_web",
        tavily_api_key="tavily",
    )


class ConversationSummaryStoreTests(unittest.TestCase):
    def test_summary_progress_survives_store_restart(self) -> None:
        rows: dict[str, tuple] = {}
        first_connection = FakeConnection(rows)
        second_connection = FakeConnection(rows)
        summary = ConversationSummary(
            conversation_id="conversation-a",
            summary="Eggs and tomatoes; user prefers less oil.",
            summarized_through_message_id="message-12",
            summarized_message_count=12,
            approximate_tokens_before=500,
            approximate_tokens_after=120,
        )

        with patch(
            "app.memory.conversation_summary.pymysql.connect",
            side_effect=[first_connection, second_connection],
        ):
            first = MySQLConversationSummaryStore(settings()).start()
            first.save(summary)
            first.close()
            restarted = MySQLConversationSummaryStore(settings()).start()
            loaded = restarted.load("conversation-a")
            missing = restarted.load("conversation-b")
            restarted.close()

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.summary, summary.summary)
        self.assertEqual(loaded.summarized_message_count, 12)
        self.assertEqual(loaded.summarized_through_message_id, "message-12")
        self.assertIsNone(missing)
        self.assertTrue(first_connection.closed)
        self.assertTrue(second_connection.closed)

    def test_delete_removes_only_the_requested_summary(self) -> None:
        rows: dict[str, tuple] = {}
        connection = FakeConnection(rows)
        first = ConversationSummary(
            conversation_id="conversation-a",
            summary="First summary",
            summarized_through_message_id="message-2",
            summarized_message_count=2,
            approximate_tokens_before=100,
            approximate_tokens_after=30,
        )
        second = ConversationSummary(
            conversation_id="conversation-b",
            summary="Second summary",
            summarized_through_message_id="message-4",
            summarized_message_count=4,
            approximate_tokens_before=180,
            approximate_tokens_after=45,
        )

        with patch(
            "app.memory.conversation_summary.pymysql.connect",
            return_value=connection,
        ):
            store = MySQLConversationSummaryStore(settings()).start()
            store.save(first)
            store.save(second)
            store.delete(first.conversation_id)

            self.assertIsNone(store.load(first.conversation_id))
            self.assertIsNotNone(store.load(second.conversation_id))
            store.close()


if __name__ == "__main__":
    unittest.main()
