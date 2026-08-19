"""Deletion of all Python-owned state for one conversation thread."""

from __future__ import annotations

import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

from app.memory.conversation_summary import (
    ConversationSummaryStore,
    ConversationSummaryStoreError,
)


class ConversationStateCleanupError(RuntimeError):
    """Raised when checkpoint or summary deletion cannot be completed."""


class ConversationStateCleaner:
    """Delete one LangGraph thread first, then its derived summary."""

    def __init__(
        self,
        checkpointer: PyMySQLSaver,
        summary_store: ConversationSummaryStore,
    ) -> None:
        self._checkpointer = checkpointer
        self._summary_store = summary_store

    def delete(self, conversation_id: str) -> None:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ConversationStateCleanupError(
                "conversation_id must be a non-empty string."
            )
        if conversation_id != conversation_id.strip() or len(conversation_id) > 150:
            raise ConversationStateCleanupError("conversation_id is invalid.")

        try:
            self._checkpointer.delete_thread(conversation_id)
            self._summary_store.delete(conversation_id)
        except (pymysql.MySQLError, ConversationSummaryStoreError) as exc:
            raise ConversationStateCleanupError(
                "Conversation Agent state could not be deleted."
            ) from exc
        except ConversationStateCleanupError:
            raise
        except Exception as exc:
            raise ConversationStateCleanupError(
                "Conversation Agent state could not be deleted."
            ) from exc
