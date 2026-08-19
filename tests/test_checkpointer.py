"""Tests for explicit checkpointer startup and shutdown ownership."""

import unittest
from unittest.mock import MagicMock, patch

from app.config.settings import Settings
from app.memory.checkpointer import (
    CheckpointerError,
    CheckpointerManager,
    CheckpointerNotStartedError,
)


def make_settings() -> Settings:
    return Settings(
        model_name="step-3.7-flash",
        model_api_key="test-model-key",
        model_base_url="https://model.example/v1",
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="cooker",
        mysql_password="test-password",
        mysql_database="agent_web",
        tavily_api_key="test-tavily-key",
    )


class CheckpointerManagerTests(unittest.TestCase):
    @patch("app.memory.checkpointer.PyMySQLSaver")
    @patch("app.memory.checkpointer.pymysql.connect")
    def test_context_starts_sets_up_and_closes_owned_connection(
        self,
        connect: MagicMock,
        saver_class: MagicMock,
    ) -> None:
        connection = connect.return_value
        saver = saver_class.return_value
        manager = CheckpointerManager(make_settings())

        with manager as started_manager:
            self.assertIs(started_manager.checkpointer, saver)

        connect.assert_called_once()
        self.assertTrue(connect.call_args.kwargs["autocommit"])
        saver_class.assert_called_once_with(connection)
        saver.setup.assert_called_once_with()
        connection.close.assert_called_once_with()

        with self.assertRaises(CheckpointerNotStartedError):
            _ = manager.checkpointer

    @patch("app.memory.checkpointer.PyMySQLSaver")
    @patch("app.memory.checkpointer.pymysql.connect")
    def test_setup_failure_closes_connection_and_remains_unstarted(
        self,
        connect: MagicMock,
        saver_class: MagicMock,
    ) -> None:
        connection = connect.return_value
        saver_class.return_value.setup.side_effect = RuntimeError("setup failed")
        manager = CheckpointerManager(make_settings())

        with self.assertRaises(CheckpointerError):
            manager.start()

        connection.close.assert_called_once_with()
        with self.assertRaises(CheckpointerNotStartedError):
            _ = manager.checkpointer


if __name__ == "__main__":
    unittest.main()
