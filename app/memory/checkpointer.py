"""Explicit lifecycle management for the LangGraph MySQL checkpointer."""

from __future__ import annotations

from types import TracebackType

import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

from app.config.settings import Settings


class CheckpointerError(RuntimeError):
    """Raised when checkpoint storage cannot be started, used, or closed."""


class CheckpointerNotStartedError(CheckpointerError):
    """Raised when code requests the saver before calling start()."""


class CheckpointerManager:
    """Own one PyMySQL connection and the saver that uses it.

    ``start()`` is intended for application startup and ``close()`` for shutdown.
    The context-manager methods make the same lifecycle convenient for the demo.
    The Agent must only be used while this manager is started.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: pymysql.connections.Connection | None = None
        self._checkpointer: PyMySQLSaver | None = None

    @property
    def checkpointer(self) -> PyMySQLSaver:
        if self._checkpointer is None:
            raise CheckpointerNotStartedError(
                "The checkpointer is not started. Call start() first."
            )
        return self._checkpointer

    def start(self) -> PyMySQLSaver:
        """Open MySQL, create the saver, and apply its idempotent setup."""

        if self._checkpointer is not None:
            return self._checkpointer

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
            checkpointer = PyMySQLSaver(connection)
            checkpointer.setup()
        except Exception as exc:
            if connection is not None:
                connection.close()
            raise CheckpointerError(
                "Unable to initialize the LangGraph MySQL checkpointer."
            ) from exc

        self._connection = connection
        self._checkpointer = checkpointer
        return checkpointer

    def close(self) -> None:
        """Close the owned connection and make the saver unavailable."""

        connection = self._connection
        self._checkpointer = None
        self._connection = None

        if connection is None:
            return

        try:
            connection.close()
        except Exception as exc:
            raise CheckpointerError(
                "Unable to close the LangGraph MySQL checkpointer connection."
            ) from exc

    def __enter__(self) -> "CheckpointerManager":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
