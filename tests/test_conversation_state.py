"""Tests for complete, thread-scoped Python state deletion."""

from __future__ import annotations

import unittest

from app.memory.conversation_state import (
    ConversationStateCleaner,
    ConversationStateCleanupError,
)


class FakeCheckpointer:
    def __init__(self) -> None:
        self.threads = {"delete-me": "checkpoint", "keep-me": "checkpoint"}
        self.deleted: list[str] = []
        self.error: Exception | None = None

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        if self.error is not None:
            raise self.error
        self.threads.pop(thread_id, None)


class FakeSummaryStore:
    def __init__(self) -> None:
        self.summaries = {"delete-me": "summary", "keep-me": "summary"}
        self.deleted: list[str] = []

    def delete(self, conversation_id: str) -> None:
        self.deleted.append(conversation_id)
        self.summaries.pop(conversation_id, None)


class ConversationStateCleanerTests(unittest.TestCase):
    def test_deletes_thread_and_summary_without_affecting_other_threads(self) -> None:
        checkpointer = FakeCheckpointer()
        summaries = FakeSummaryStore()
        cleaner = ConversationStateCleaner(
            checkpointer,  # type: ignore[arg-type]
            summaries,  # type: ignore[arg-type]
        )

        cleaner.delete("delete-me")

        self.assertEqual(checkpointer.deleted, ["delete-me"])
        self.assertEqual(summaries.deleted, ["delete-me"])
        self.assertNotIn("delete-me", checkpointer.threads)
        self.assertNotIn("delete-me", summaries.summaries)
        self.assertIn("keep-me", checkpointer.threads)
        self.assertIn("keep-me", summaries.summaries)

    def test_checkpoint_failure_does_not_delete_summary(self) -> None:
        checkpointer = FakeCheckpointer()
        checkpointer.error = RuntimeError("database unavailable")
        summaries = FakeSummaryStore()
        cleaner = ConversationStateCleaner(
            checkpointer,  # type: ignore[arg-type]
            summaries,  # type: ignore[arg-type]
        )

        with self.assertRaises(ConversationStateCleanupError):
            cleaner.delete("delete-me")

        self.assertEqual(summaries.deleted, [])
        self.assertIn("delete-me", summaries.summaries)

    def test_deletion_is_idempotent(self) -> None:
        checkpointer = FakeCheckpointer()
        summaries = FakeSummaryStore()
        cleaner = ConversationStateCleaner(
            checkpointer,  # type: ignore[arg-type]
            summaries,  # type: ignore[arg-type]
        )

        cleaner.delete("delete-me")
        cleaner.delete("delete-me")

        self.assertEqual(checkpointer.deleted, ["delete-me", "delete-me"])
        self.assertEqual(summaries.deleted, ["delete-me", "delete-me"])


if __name__ == "__main__":
    unittest.main()
