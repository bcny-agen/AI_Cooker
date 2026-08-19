"""Isolated Recipe KB configuration; never reuses application MySQL settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


class RecipeKBConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecipeKBConfig:
    host: str = "127.0.0.1"
    port: int = 55432
    database: str = "recipe_kb"
    user: str = "recipe_kb"
    password: str = ""
    connect_timeout_seconds: int = 5
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dimension: int = 384
    embedding_batch_size: int = 16
    embedding_device: str = "cpu"

    @classmethod
    def from_env(cls, *, require_password: bool = True) -> "RecipeKBConfig":
        password = os.getenv("RECIPE_DB_PASSWORD", "")
        if require_password and not password:
            raise RecipeKBConfigurationError("RECIPE_DB_PASSWORD is required")
        config = cls(
            host=os.getenv("RECIPE_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("RECIPE_DB_PORT", "55432")),
            database=os.getenv("RECIPE_DB_NAME", "recipe_kb"),
            user=os.getenv("RECIPE_DB_USER", "recipe_kb"),
            password=password,
            connect_timeout_seconds=int(os.getenv("RECIPE_DB_CONNECT_TIMEOUT_SECONDS", "5")),
            embedding_provider=os.getenv("RECIPE_EMBEDDING_PROVIDER", "sentence-transformers"),
            embedding_model=os.getenv(
                "RECIPE_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
            ),
            embedding_dimension=int(
                os.getenv(
                    "RECIPE_EMBEDDING_DIMENSION",
                    os.getenv("RECIPE_EMBEDDING_DIMENSIONS", "384"),
                )
            ),
            embedding_batch_size=int(os.getenv("RECIPE_EMBEDDING_BATCH_SIZE", "16")),
            embedding_device=os.getenv("RECIPE_EMBEDDING_DEVICE", "cpu"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not (1 <= self.port <= 65535):
            raise RecipeKBConfigurationError("RECIPE_DB_PORT is invalid")
        if not self.host or not self.database or not self.user:
            raise RecipeKBConfigurationError("Recipe DB host, name, and user are required")
        if self.embedding_dimension != 384 and self.embedding_model == "intfloat/multilingual-e5-small":
            raise RecipeKBConfigurationError(
                "intfloat/multilingual-e5-small is frozen at 384 dimensions"
            )
        if self.embedding_batch_size < 1:
            raise RecipeKBConfigurationError("RECIPE_EMBEDDING_BATCH_SIZE must be positive")

    @property
    def connection_kwargs(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": self.connect_timeout_seconds,
        }

    def __repr__(self) -> str:
        return (
            "RecipeKBConfig("
            f"host={self.host!r}, port={self.port!r}, database={self.database!r}, "
            f"user={self.user!r}, password='<redacted>', "
            f"embedding_model={self.embedding_model!r}, "
            f"embedding_dimension={self.embedding_dimension!r})"
        )
