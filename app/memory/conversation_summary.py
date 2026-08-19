"""Python-owned persistence for conversation-scoped inference summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol

import pymysql

from app.config.settings import Settings


RECOVERED_SUMMARY_REFERENCE = "recovered:external-history"


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Last valid incremental summary and its checkpoint-message progress."""

    conversation_id: str
    summary: str
    summarized_through_message_id: str
    summarized_message_count: int
    approximate_tokens_before: int
    approximate_tokens_after: int
    updated_at: datetime | None = None


class ConversationSummaryStore(Protocol):
    def load(self, conversation_id: str) -> ConversationSummary | None: ...

    def save(self, summary: ConversationSummary) -> None: ...

    def delete(self, conversation_id: str) -> None: ...


class ConversationSummaryStoreError(RuntimeError):
    """Raised when the application-managed summary store cannot be used."""


class MySQLConversationSummaryStore:
    """Own a dedicated MySQL connection for Agent context summaries."""

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            conversation_id VARCHAR(150) NOT NULL,
            summary LONGTEXT NOT NULL,
            summarized_through_message_id VARCHAR(255) NOT NULL,
            summarized_message_count INT UNSIGNED NOT NULL,
            approximate_tokens_before INT UNSIGNED NOT NULL,
            approximate_tokens_after INT UNSIGNED NOT NULL,
            updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            PRIMARY KEY (conversation_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: pymysql.connections.Connection | None = None

    def start(self) -> "MySQLConversationSummaryStore":
        if self._connection is not None:
            return self

        connection: pymysql.connections.Connection | None = None
        try:
            connection = pymysql.connect(
                host=self._settings.mysql_host,
                port=self._settings.mysql_port,
                user=self._settings.mysql_user,
                password=self._settings.mysql_password,
                database=self._settings.mysql_database,
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=10,
                read_timeout=60,
                write_timeout=60,
            )
            with connection.cursor() as cursor:
                cursor.execute(self._CREATE_TABLE)
        except Exception as exc:
            if connection is not None:
                connection.close()
            raise ConversationSummaryStoreError(
                "Unable to initialize the conversation summary store."
            ) from exc

        self._connection = connection
        return self

    def load(self, conversation_id: str) -> ConversationSummary | None:
        connection = self._require_connection()
        connection.ping(reconnect=True)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT summary,
                       summarized_through_message_id,
                       summarized_message_count,
                       approximate_tokens_before,
                       approximate_tokens_after,
                       updated_at
                FROM conversation_summaries
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ConversationSummary(
            conversation_id=conversation_id,
            summary=str(row[0]),
            summarized_through_message_id=str(row[1]),
            summarized_message_count=int(row[2]),
            approximate_tokens_before=int(row[3]),
            approximate_tokens_after=int(row[4]),
            updated_at=row[5],
        )

    def save(self, summary: ConversationSummary) -> None:
        connection = self._require_connection()
        connection.ping(reconnect=True)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_summaries (
                    conversation_id,
                    summary,
                    summarized_through_message_id,
                    summarized_message_count,
                    approximate_tokens_before,
                    approximate_tokens_after
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    summary = VALUES(summary),
                    summarized_through_message_id =
                        VALUES(summarized_through_message_id),
                    summarized_message_count = VALUES(summarized_message_count),
                    approximate_tokens_before = VALUES(approximate_tokens_before),
                    approximate_tokens_after = VALUES(approximate_tokens_after),
                    updated_at = CURRENT_TIMESTAMP(6)
                """,
                (
                    summary.conversation_id,
                    summary.summary,
                    summary.summarized_through_message_id,
                    summary.summarized_message_count,
                    summary.approximate_tokens_before,
                    summary.approximate_tokens_after,
                ),
            )

    def delete(self, conversation_id: str) -> None:
        connection = self._require_connection()
        connection.ping(reconnect=True)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM conversation_summaries
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.close()
        except Exception as exc:
            raise ConversationSummaryStoreError(
                "Unable to close the conversation summary store."
            ) from exc

    def _require_connection(self) -> pymysql.connections.Connection:
        if self._connection is None:
            raise ConversationSummaryStoreError(
                "The conversation summary store has not been started."
            )
        return self._connection

    def __enter__(self) -> "MySQLConversationSummaryStore":
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
